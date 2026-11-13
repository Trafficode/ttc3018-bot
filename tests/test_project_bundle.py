# ---------------------------------------------------------------------------
# test_project_bundle.py
# 2026-11-13
# - Semantic THT classification, stage integrity and independent capabilities.
# ---------------------------------------------------------------------------
"""Tests never connect to a machine or use station files."""

import io
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

from monitor.library import PackageLibrary
from monitor.pcb_flow import mechanical_programs, validate_flow
from monitor.project_bundle import read_bundle, bundle_summary
from project_fixture import project_archive, zip_files
from test_cam import package
from test_simple_drilling import simple_values


class ProjectBundleTests(unittest.TestCase):
    """All stage metadata belongs to exactly the same source board."""

    def setUp(self):
        self.source = project_archive()
        self.project = package(self.source)["project"]

    def test_import_persists_stage_capabilities_and_known_tht_diameters(self):
        with tempfile.TemporaryDirectory() as directory:
            library = PackageLibrary(Path(directory))
            imported = library.import_package(package(self.source))["package"]
            record = imported["files"][0]
            self.assertEqual(record["machining"]["version"], 1)
            self.assertEqual(record["machining"]["stages"]["drilling"][
                "diametersMm"], [.8, 1.2])
            self.assertEqual(library.get(imported["id"]), imported)

    def test_new_drilling_uses_only_semantic_tht_not_legacy_via_file(self):
        values = validate_flow({"operations": ["drilling"],
            "operationSettings": {"drilling": simple_values()},
            "thicknessMm": 1, "confirmedSetup": True})
        with tempfile.TemporaryDirectory() as directory:
            operations, files = mechanical_programs(self.source,
                {"matrix": [-1, 0, 0, 1, 20, 0]},
                {"bounds": [0, 0, 20, 20]}, values, 3, Path(directory))
        self.assertEqual([item["diameterMm"] for item in operations], [.8, 1.2])
        self.assertEqual(operations[0]["points"], [[18, 3]])
        self.assertEqual(len(files), 2)

    def test_unsupported_or_empty_tht_does_not_disable_other_stages(self):
        for source in (project_archive(holes=[]), project_archive(
            unsupported=[{"id": "slot", "reason": "slot"}])):
            summary = bundle_summary(source, self.project)
            self.assertFalse(summary["stages"]["drilling"]["available"])
            self.assertTrue(summary["stages"]["isolation"]["available"])
            self.assertTrue(summary["stages"]["outline"]["available"])

    def test_wrong_source_side_or_hash_is_rejected(self):
        for change in ({"boardHash": "b" * 64}, {"side": "F.Cu"}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                read_bundle(self.source, {**self.project, **change}, True)
        with zipfile.ZipFile(io.BytesIO(self.source)) as archive:
            files = {name: archive.read(name) for name in archive.namelist()}
        files["fixture-B_Cu.gbl"] += b"tampered"
        with self.assertRaisesRegex(ValueError, "Zmieniony"):
            read_bundle(zip_files(files), self.project, True)

    def test_non_tht_duplicate_and_nonfinite_holes_are_rejected(self):
        base = {"id": "pad", "role": "tht", "x": 2, "y": 3,
                "diameterMm": .8}
        for holes in ([{**base, "role": "via"}], [base, base],
                      [{**base, "x": float("nan")}],
                      [{**base, "diameterMm": True}]):
            with self.subTest(holes=holes), self.assertRaises(ValueError):
                read_bundle(project_archive(holes), self.project, True)

    def test_traversal_and_duplicate_files_are_rejected(self):
        with zipfile.ZipFile(io.BytesIO(self.source)) as archive:
            files = {name: archive.read(name) for name in archive.namelist()}
        files["../escape"] = b"invalid"
        with self.assertRaises(ValueError):
            read_bundle(zip_files(files), self.project, True)

    def test_legacy_package_has_no_claimed_tht_classification(self):
        from test_cam import archive
        summary = bundle_summary(archive(), self.project)
        self.assertEqual(summary["version"], 0)
        self.assertFalse(summary["stages"]["drilling"]["available"])


if __name__ == "__main__":
    unittest.main()

# ---------------------------------------------------------------------------
# end of file
# ---------------------------------------------------------------------------
