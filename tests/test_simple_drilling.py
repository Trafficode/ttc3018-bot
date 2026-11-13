# ---------------------------------------------------------------------------
# test_simple_drilling.py
# 2026-11-13
# - Explicit tip depth, fixed spindle and deliberate legacy profile updates.
# ---------------------------------------------------------------------------
"""Only temporary source data and mocked controllers; never physical CNC."""

from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock

from monitor.jobs import parse_program
from monitor.pcb_flow import validate_tool_values, validate_flow
from monitor.process_profiles import ProcessProfiles
from test_independent_tools import flow, tool_values
from test_pcb_flow import drills
from controller_fixture import Controller

try:
    import gerbonara
    GEOMETRY = True
except ImportError:
    GEOMETRY = False


def simple_values(**extra):
    """Explicit fixture values, not a recommended physical cutting recipe."""
    return {"drillDiameterMm": 0, "drillFeed": 17,
            "drillOverrunMm": .6, "clearanceMm": 3, **extra}


class SimpleProfileTests(unittest.TestCase):
    """No hidden dimensions or automatic reinterpretation of stored values."""

    def test_only_four_values_required_and_obsolete_overrides_are_ignored(self):
        values = simple_values(drillPower=200, drillPointAngleDeg=60,
                               backingMm=.1, uncertaintyMm=100)
        self.assertEqual(validate_tool_values(values, "drilling"),
                         simple_values())

    def test_overrun_is_required_finite_and_bounded(self):
        for value in (None, True, float("nan"), float("inf"), 0, 5.1):
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_tool_values(simple_values(drillOverrunMm=value),
                                     "drilling")
        missing = simple_values()
        del missing["drillOverrunMm"]
        with self.assertRaises(ValueError):
            validate_tool_values(missing, "drilling")

    def test_legacy_file_is_unchanged_until_explicitly_saved(self):
        with tempfile.TemporaryDirectory() as temporary:
            filename = Path(temporary) / "profiles.json"
            store = ProcessProfiles(filename)
            old = store.save({"kind": "drilling", "name": "Legacy",
                              "values": tool_values("drilling"),
                              "confirmedTools": True}, {})
            original = filename.read_bytes()
            restored = ProcessProfiles(filename)
            self.assertIsNone(restored.error)
            self.assertEqual(restored.get(old["id"]), old)
            self.assertEqual(filename.read_bytes(), original)
            updated = restored.save({"kind": "drilling", "name": "Simple",
                "values": simple_values(), "confirmedTools": True,
                "id": old["id"], "expectedFingerprint": old["fingerprint"]}, {})
            self.assertEqual(updated["revision"], 2)
            self.assertEqual(updated["values"], simple_values())
            self.assertNotIn("drillPower", updated["values"])
            with self.assertRaises(ValueError):
                restored.assert_snapshot(old)
            self.assertIsNone(ProcessProfiles(filename).error)

    def test_resolve_uses_saved_overrun_without_hidden_tool_overrides(self):
        with tempfile.TemporaryDirectory() as temporary:
            store = ProcessProfiles(Path(temporary) / "profiles.json")
            saved = store.save({"kind": "drilling", "name": "Simple",
                                "values": simple_values(),
                                "confirmedTools": True}, {})
            _, result, _ = store.resolve({
                "operations": ["drilling"], "confirmedSetup": True,
                "processProfiles": {"drilling": {
                    "id": saved["id"], "fingerprint": saved["fingerprint"]}},
                "material": {"thicknessMm": 1, "drillOverrunMm": 4}}, {})
            self.assertEqual(result["operationSettings"]["drilling"],
                             simple_values())


@unittest.skipUnless(GEOMETRY, "Install requirements-cam.txt")
class SimpleGeometryTests(unittest.TestCase):
    """Real Excellon holes keep diameter grouping and exact requested depth."""

    def test_each_diameter_uses_thickness_plus_overrun_and_fixed_spindle(self):
        from monitor.pcb_flow import mechanical_programs
        with tempfile.TemporaryDirectory() as temporary:
            settings = flow(["drilling"])
            settings["operationSettings"]["drilling"] = simple_values()
            operations, programs = mechanical_programs(
                drills(), {"matrix": [-1, 0, 0, 1, 20, 0]},
                {"bounds": [0, 0, 20, 20]}, validate_flow(settings), 3,
                Path(temporary))
            self.assertEqual([value["diameterMm"] for value in operations],
                             [.8, 1.2])
            for operation in operations:
                self.assertEqual(operation["depthMm"], 1.6)
                self.assertEqual(operation["drillOverrunMm"], .6)
                self.assertNotIn("uncertaintyMm", operation)
                self.assertNotIn("breakthroughMm", operation)
                content = programs[operation["file"]]
                self.assertIn("M3 S1000", content)
                self.assertIn("G1 Z-1.60000 F17", content)


class SimpleStartTests(unittest.TestCase):
    """Fresh-Z checks remain mandatory; legacy allowance fields are absent."""

    def setUp(self):
        self.cnc = Controller()
        self.cnc.port = Mock()
        self.cnc.jobs.load(parse_program("simple.nc", (
            "G21 G90 G94 G54\nG0 Z3\nG0 X0 Y0\n"
            "G1 Z-1.6 F17\nG0 Z3\nM5\nM30")))
        self.cnc.jobs.program["pcb_flow"] = {
            "kind": "drilling", "zPreparation": "point", "xyOffset": [0, 0],
            "drillOverrunMm": .6, "surfaceSpreadMm": .1}

    def test_new_depth_still_requires_matching_point_probe(self):
        with self.assertRaisesRegex(ValueError, "nowy pomiar"):
            self.cnc.action("job_start", {
                "job_id": self.cnc.jobs.job_id, "confirmed": True})
        self.cnc.port.write.assert_not_called()

    def test_fresh_probe_allows_explicit_start_without_removed_fields(self):
        self.cnc.probe.completed_job_id = self.cnc.jobs.job_id
        self.cnc.probe.completed_offset = [0, 0, 0]
        self.cnc._line = Mock(side_effect=lambda command: (
            ["[G54:0,0,0]", "[G92:0,0,0]", "[TLO:0]"]
            if command == "$#" else ["[GC:G54 M5]"]))
        self.cnc._status = Mock()
        self.cnc.report = {"state": "Idle", "position": [0, 0, 1]}
        self.cnc.action("job_start", {
            "job_id": self.cnc.jobs.job_id, "confirmed": True})
        self.assertEqual(self.cnc.jobs.state, "running")
        self.cnc.port.write.assert_not_called()


if __name__ == "__main__":
    unittest.main()

# ---------------------------------------------------------------------------
# end of file
# ---------------------------------------------------------------------------
