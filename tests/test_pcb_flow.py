# ---------------------------------------------------------------------------
# test_pcb_flow.py
# 2026-11-09
# - Mechanical CAM, material validation, shared datum and completion evidence.
# ---------------------------------------------------------------------------
"""Hardware-free flow tests use real Gerber/Excellon parsers and fake status."""

import copy
import io
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import Mock
import zipfile

from monitor.jobs import parse_program
from monitor.pcb_progress import PcbProgress
from monitor.surfaces import plan_grid
from monitor.compensation import height_at
from types import SimpleNamespace
from controller_fixture import Controller

try:
    from monitor.pcb_flow import mechanical_programs, validate_flow
    GEOMETRY = True
except ImportError:
    GEOMETRY = False


def settings():
    """Explicit test parameters, never a recommended machine cutting recipe."""
    return {"thicknessMm": 1, "skinMm": .2, "uncertaintyMm": .05,
            "backingMm": 5, "breakthroughMm": .2,
            "drillPointAngleDeg": 118, "stepDownMm": .2,
            "cuttingLengthMm": 3, "drillFeed": 10, "drillPower": 900,
            "millFeed": 60, "millPlunge": 5, "millPower": 800,
            "millDiameterMm": 1, "tabWidthMm": 3, "tabHeightMm": .3,
            "retention": "skin", "confirmedSetup": True}


def drills():
    """Two round hole diameters in a declared metric Excellon file."""
    result = io.BytesIO()
    with zipfile.ZipFile(result, "w") as archive:
        archive.writestr("fixture-PTH.drl", "M48\nMETRIC\nT1C0.8\n"
                         "T2C1.2\n%\nG90\nT1\nX2.0Y3.0\n"
                         "X4.0Y5.0\nT2\nX6.0Y7.0\nM30\n")
    return result.getvalue()


@unittest.skipUnless(GEOMETRY, "Install requirements-cam.txt")
class MechanicalTests(unittest.TestCase):
    """Check actual generated commands against known geometry and depths."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.transform = {"matrix": [-1, 0, 0, 1, 20, 0]}

    def generate(self, values=None):
        return mechanical_programs(drills(), self.transform,
                                   {"bounds": [0, 0, 20, 20]},
                                   validate_flow(values or settings()),
                                   3, self.root)

    def test_material_required_and_retention_limits(self):
        for key, value in (("thicknessMm", None), ("thicknessMm", True),
                           ("skinMm", 1), ("uncertaintyMm", .2),
                           ("cuttingLengthMm", .5),
                           ("confirmedSetup", False)):
            with self.assertRaises(ValueError):
                validate_flow({**settings(), key: value})

    def test_drills_grouped_and_same_mirror_applied(self):
        operations, files = self.generate()
        self.assertEqual([value["kind"] for value in operations],
                         ["drilling", "drilling", "outline"])
        self.assertEqual(operations[0]["points"], [[18, 3], [16, 5]])
        self.assertEqual(operations[0]["holes"], 2)
        self.assertGreater(operations[0]["depthMm"], 1.2)
        self.assertIn("G0 X18.00000 Y3.00000", files["drill-00.nc"])
        for name, content in files.items():
            parsed = parse_program(name, content)
            self.assertIsNone(parsed["cam_profile"])
            self.assertIn("M5", content)
            self.assertNotIn("M6", content)

    def test_outline_skin_depth_offset_and_passes(self):
        operations, files = self.generate()
        outline = operations[-1]
        program = parse_program("outline.nc", files["outline.nc"])
        self.assertEqual(outline["passes"], 4)
        self.assertEqual(program["bounds_mm"]["Z"], [-.8, 3])
        self.assertEqual(program["bounds_mm"]["X"], [-.5, 20.5])
        self.assertEqual(program["bounds_mm"]["Y"], [-.5, 20.5])

    def test_tabs_retain_four_spans_at_final_depth(self):
        operations, files = self.generate({**settings(), "retention": "tabs"})
        program = parse_program("outline.nc", files["outline.nc"])
        self.assertEqual(program["bounds_mm"]["Z"][0], -1.2)
        self.assertGreaterEqual(files["outline.nc"].count("G1 Z-0.70000"), 4)
        self.assertEqual(operations[-1]["retention"], "tabs")

    def test_insufficient_backing_rejected(self):
        with self.assertRaisesRegex(ValueError, "Podkład"):
            self.generate({**settings(), "backingMm": 1})


class PerimeterTests(unittest.TestCase):
    """Eight measured frame points suffice for the boundary-only cut."""

    def test_eight_points_omit_centre(self):
        area, points = plan_grid({"X": [-.5, 20.5], "Y": [-.5, 20.5]},
                                 {"columns": 3, "rows": 3,
                                  "area": {"X": [-.5, 20.5],
                                           "Y": [-.5, 20.5]},
                                  "perimeterOnly": True})
        self.assertEqual(len(points), 8)
        self.assertFalse(any(p["x"] == 10 and p["y"] == 10 for p in points))
        surface = SimpleNamespace(area=area, columns=3, rows=3, perimeter=True,
                                  samples=[{"z": p["x"]*.001 + p["y"]*.002}
                                           for p in points])
        for x, y in ((-.5, 3), (20.5, 8), (6, -.5), (13, 20.5)):
            self.assertAlmostEqual(height_at(surface, x, y), x*.001+y*.002)


class ProgressTests(unittest.TestCase):
    """No manual completion, phase skipping or stale server-session evidence."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.collection = Mock()
        self.collection.lock = threading.RLock()
        self.collection.directory.return_value = Path(self.temp.name)
        self.progress = PcbProgress(self.collection)

    def test_only_exact_completed_sender_job_advances(self):
        filename = Path(self.temp.name) / "progress.json"
        filename.write_text(json.dumps({"completed": [], "loaded": {
            "index": 0, "session": self.progress.session, "jobId": "exact"}}))
        self.assertEqual(self.progress.read("fixture", {"job": {
            "id": "other", "state": "completed"}})["completed"], [])
        self.assertEqual(self.progress.read("fixture", {"job": {
            "id": "exact", "state": "failed"}})["completed"], [])
        self.assertEqual(self.progress.read("fixture", {"job": {
            "id": "exact", "state": "completed"}})["completed"], [0])

    def test_restart_never_accepts_old_completion(self):
        (Path(self.temp.name) / "progress.json").write_text(json.dumps({
            "completed": [], "loaded": {"index": 0, "session": "old",
                                          "jobId": "exact"}}))
        result = self.progress.read("fixture", {"job": {
            "id": "exact", "state": "completed"}})
        self.assertEqual(result["completed"], [])
        self.assertTrue(result["requiresReload"])


class StartGateTests(unittest.TestCase):
    """Check new interlocks before any fake serial write can take place."""

    def setUp(self):
        self.cnc = Controller()
        self.cnc.port = Mock()
        self.cnc.jobs.load(parse_program("fixture.nc", (
            "G21 G90 G94 G54\nG0 Z3\nG0 X0 Y0\n"
            "G1 Z-0.8 F5\nG1 X1 F60\nG0 Z3\nM5\nM30")))

    def attempt(self, operation, expected):
        self.cnc.jobs.program["pcb_flow"] = operation
        with self.assertRaisesRegex(ValueError, expected):
            self.cnc.action("job_start", {
                "job_id": self.cnc.jobs.job_id, "confirmed": True})
        self.cnc.port.write.assert_not_called()

    def test_drill_requires_new_point_probe(self):
        self.attempt({"kind": "drilling", "zPreparation": "point"},
                     "nowy pomiar")

    def test_outline_requires_new_map(self):
        self.attempt({"kind": "outline", "zPreparation": "grid3"},
                     "nowej mapy")

    def test_repeated_completed_operation_requires_reload(self):
        self.cnc.jobs.state = "completed"
        self.attempt({"kind": "outline", "zPreparation": "grid3"},
                     "ponownie")

    def test_fresh_drill_zero_allows_explicit_start_without_usb_write(self):
        self.cnc.jobs.program["pcb_flow"] = {
            "kind": "drilling", "zPreparation": "point", "xyOffset": [0, 0],
            "breakthroughMm": .2, "uncertaintyMm": .05}
        self.cnc.probe.completed_job_id = self.cnc.jobs.job_id
        self.cnc.probe.completed_offset = [0, 0, 0]
        self.cnc._line = Mock(side_effect=lambda command: (
            ["[G54:0,0,0]", "[G92:0,0,0]", "[TLO:0]"]
            if command == "$#" else ["[GC:G54 M5]"]))
        self.cnc._status = Mock()
        self.cnc.report = {"state": "Idle", "position": [0, 0, 1]}
        result = self.cnc.action("job_start", {
            "job_id": self.cnc.jobs.job_id, "confirmed": True})
        self.assertIn("lease", result)
        self.assertEqual(self.cnc.jobs.state, "running")
        self.cnc.port.write.assert_not_called()


if __name__ == "__main__":
    unittest.main()

# ---------------------------------------------------------------------------
# end of file
# ---------------------------------------------------------------------------
