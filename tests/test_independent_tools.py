# ---------------------------------------------------------------------------
# test_independent_tools.py
# 2026-11-13
# - Independent tool recipes and exact selected-operation CAM output.
# ---------------------------------------------------------------------------
"""Temporary stores, real source fixtures and mocked workers; no hardware."""

import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch
import zipfile

from monitor.cam import CamCollection
from monitor.library import PackageLibrary
from monitor.pcb_flow import validate_flow, validate_tool_values
from monitor.process_profiles import ProcessProfiles
from test_cam import archive, package, profile
from test_pcb_flow import drills, settings

try:
    import gerbonara
    import shapely
    GEOMETRY = True
except ImportError:
    GEOMETRY = False


def tool_values(kind):
    """Explicit fixture values, never recommended physical cutting settings."""
    values = {**settings(), "clearanceMm": 3, "drillDiameterMm": 0}
    return validate_tool_values(values, kind)


def flow(kinds, **extra):
    """Only selected tools contribute settings and one measured thickness."""
    return {"operations": kinds, "thicknessMm": 1,
            "operationSettings": {kind: tool_values(kind) for kind in kinds
                                  if kind != "isolation"},
            "confirmedSetup": True, **extra}


class IndependentRecipeTests(unittest.TestCase):
    """Mechanical profiles neither require nor select V-bit calibration."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "profiles.json"
        self.store = ProcessProfiles(self.path)

    def save(self, kind, **extra):
        return self.store.save({"kind": kind, "name": kind,
                                "values": tool_values(kind),
                                "confirmedTools": True, **extra}, {})

    def resolve(self, saved, kinds=None, **extra):
        return self.store.resolve({
            "operations": kinds or list(saved), "confirmedSetup": True,
            "processProfiles": {kind: {"id": value["id"],
                                      "fingerprint": value["fingerprint"]}
                                for kind, value in saved.items()},
            "material": {"thicknessMm": 1}, **extra}, {})

    def test_independent_save_select_and_reload_without_v_model(self):
        saved = {kind: self.save(kind) for kind in ("drilling", "outline")}
        for kind, value in saved.items():
            self.assertNotIn("isolation", value)
            self.assertNotIn("thicknessMm", value["values"])
            self.store.select({"id": value["id"], "kind": kind,
                               "fingerprint": value["fingerprint"]})
        restored = ProcessProfiles(self.path)
        self.assertIsNone(restored.error)
        self.assertEqual(restored.status()["activeByKind"],
                         {kind: value["id"] for kind, value in saved.items()})
        snapshot, result, height = self.resolve(saved)
        self.assertEqual(result["operations"], ["drilling", "outline"])
        self.assertEqual(height, 3)
        self.store.assert_snapshot(snapshot)

    def test_wrong_kind_and_stale_aggregate_rejected(self):
        saved = {"drilling": self.save("drilling")}
        with self.assertRaisesRegex(ValueError, "rodzaju"):
            self.store.select({**saved["drilling"], "kind": "outline"})
        snapshot, _, _ = self.resolve(saved)
        changed = {**tool_values("drilling"), "drillFeed": 25}
        self.save("drilling", id=saved["drilling"]["id"], values=changed,
                  expectedFingerprint=saved["drilling"]["fingerprint"])
        with self.assertRaisesRegex(ValueError, "oblicz PCB ponownie"):
            self.store.assert_snapshot(snapshot)
        with self.assertRaisesRegex(ValueError, "zmienił"):
            self.resolve(saved)

    def test_legacy_recipe_preserved_and_used_without_calibration_binding(self):
        legacy = self.store.save({"name": "Legacy",
                                  "values": {**settings(), "clearanceMm": 3},
                                  "confirmedTools": True}, profile())
        self.save("drilling")
        restored = ProcessProfiles(self.path)
        self.assertEqual(restored.get(legacy["id"]), legacy)
        _, result, _ = self.resolve({"drilling": legacy})
        self.assertEqual(result["operationSettings"]["drilling"][
            "drillDiameterMm"], 0)

    def test_separate_values_and_visible_isolation_clearance_are_retained(self):
        drill = self.save("drilling", values={**tool_values("drilling"),
                                              "drillFeed": 17})
        outline = self.save("outline", values={**tool_values("outline"),
                                                "millFeed": 87})
        _, result, clearance = self.resolve(
            {"drilling": drill, "outline": outline},
            ["isolation", "drilling", "outline"], clearanceMm=6)
        self.assertEqual(clearance, 6)
        self.assertEqual(result["operationSettings"]["drilling"][
            "drillFeed"], 17)
        self.assertEqual(result["operationSettings"]["outline"][
            "millFeed"], 87)

    def test_through_cut_requires_job_specific_workholding_confirmation(self):
        values = {**tool_values("outline"), "retention": "through"}
        saved = self.save("outline", values=values)
        with self.assertRaisesRegex(ValueError, "mocowanie"):
            self.resolve({"outline": saved})
        _, result, _ = self.resolve({"outline": saved}, material={
            "thicknessMm": 1, "confirmedThroughCut": True})
        self.assertTrue(result["confirmedThroughCut"])

    def test_broken_per_kind_selection_is_reported_without_overwrite(self):
        self.save("drilling")
        data = json.loads(self.path.read_text())
        data["activeByKind"]["outline"] = "missing"
        self.path.write_text(json.dumps(data))
        self.assertTrue(ProcessProfiles(self.path).error)


@unittest.skipUnless(GEOMETRY, "Install requirements-cam.txt")
class IndependentGeometryTests(unittest.TestCase):
    """Exercise actual hole parsing, tool-radius offsets and worker output."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def generate(self, values, source=None):
        from monitor.pcb_flow import mechanical_programs
        return mechanical_programs(
            drills() if source is None else source,
            {"matrix": [-1, 0, 0, 1, 20, 0]},
            {"bounds": [0, 0, 20, 20]}, validate_flow(values), 3, self.root)

    def test_drilling_only_keeps_each_source_diameter_and_own_feed(self):
        values = flow(["drilling"])
        values["operationSettings"]["drilling"].update(
            drillFeed=17, drillPower=650, clearanceMm=5)
        operations, programs = self.generate(values)
        self.assertEqual([item["diameterMm"] for item in operations], [.8, 1.2])
        self.assertEqual(set(programs), {"drill-00.nc", "drill-01.nc"})
        self.assertIn("G0 Z5", programs["drill-00.nc"])
        self.assertIn("M3 S650", programs["drill-00.nc"])
        self.assertIn("F17", programs["drill-00.nc"])
        values["operationSettings"]["drilling"]["drillDiameterMm"] = .8
        with self.assertRaisesRegex(ValueError, "Średnica"):
            self.generate(values)

    def test_outline_only_uses_real_radius_and_needs_no_drill_files(self):
        values = flow(["outline"])
        values["operationSettings"]["outline"]["millDiameterMm"] = 2
        operations, programs = self.generate(values, archive())
        self.assertEqual(set(programs), {"outline.nc"})
        self.assertEqual(operations[0]["path"][0], (-1, -1))
        self.assertEqual(operations[0]["depthMm"], .8)

    @unittest.skipIf(sys.platform == "win32", "Linux worker resource sandbox")
    def test_worker_finalizes_each_mechanical_scope_without_v_profile(self):
        source = io.BytesIO(archive())
        with zipfile.ZipFile(io.BytesIO(drills())) as holes:
            with zipfile.ZipFile(source, "a") as target:
                target.writestr("fixture-PTH.drl", holes.read(
                    "fixture-PTH.drl"))
        library = PackageLibrary(self.root / "library")
        imported = library.import_package(package(source.getvalue()))["package"]
        for kinds in (["drilling"], ["outline"], ["drilling", "outline"]):
            collection = CamCollection(self.root / "-".join(kinds), library)
            payload = {"packageId": imported["id"], "name": "cad.zip",
                       "clearanceMm": 3, "confirmedDatum": True,
                       "workflow": flow(kinds)}
            with patch("monitor.cam.threading.Thread"):
                item = collection.start(payload, {})
            directory = collection.directory(item["id"])
            self.assertEqual(item["profile"], {})
            subprocess.run([sys.executable, "-m", "monitor.cam_worker",
                            str(directory)], check=True, timeout=30)
            fake = MagicMock()
            fake.wait.return_value = 0
            with patch("monitor.cam.subprocess.Popen", return_value=fake):
                collection._run(item["id"])
            finished = collection.get(item["id"])
            self.assertEqual(finished["state"], "ready", finished)
            self.assertNotIn("isolation.nc", finished["artifacts"])
            sequence = finished["report"]["sequence"]
            self.assertEqual(set(record["kind"] for record in sequence),
                             set(kinds))
            for record in sequence:
                self.assertIn("M5", collection.program(
                    item["id"], {}, record["file"])["content"])


if __name__ == "__main__":
    unittest.main()

# ---------------------------------------------------------------------------
# end of file
# ---------------------------------------------------------------------------
