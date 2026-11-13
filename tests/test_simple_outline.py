# ---------------------------------------------------------------------------
# test_simple_outline.py
# 2026-11-13
# - Conditional outline inputs, optional defaults and exact retained material.
# ---------------------------------------------------------------------------
"""Use temporary stores and generated NC only; never physical CNC controls."""

from pathlib import Path
import tempfile
import unittest

from monitor.jobs import parse_program
from monitor.pcb_flow import (
    mechanical_programs, resolved_outline_settings, validate_flow,
    validate_tool_values,
)
from monitor.process_profiles import ProcessProfiles
from test_independent_tools import tool_values


def values(retention="skin", **extra):
    """Fixture values are not a universal physical cutting recipe."""
    result = {"outlineDepthMode": "remaining", "millDiameterMm": 1,
              "millFeed": 60, "millPlunge": 5, "clearanceMm": 3,
              "retention": retention}
    if retention != "through":
        result["remainingMm"] = .3
    if retention != "skin":
        result["millOverrunMm"] = .2
    return {**result, **extra}


def workflow(settings, **extra):
    """A single selected tool and one measured stock thickness."""
    return {"operations": ["outline"], "thicknessMm": 1,
            "operationSettings": {"outline": settings},
            "confirmedSetup": True, **extra}


class SimpleOutlineTests(unittest.TestCase):
    """Core fields suffice; actual pass and tab defaults resolve on the server."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def generate(self, settings, **extra):
        return mechanical_programs(
            b"", {}, {"bounds": [0, 0, 20, 20]},
            validate_flow(workflow(settings, **extra)), 3, self.root)

    def test_core_fields_save_reload_and_resolve_without_overrides(self):
        store = ProcessProfiles(self.root / "profiles.json")
        saved = store.save({"kind": "outline", "name": "Simple",
                            "values": values(), "confirmedTools": True}, {})
        self.assertEqual(saved["values"], values())
        self.assertIsNone(ProcessProfiles(store.filename).error)
        _, plan, _ = store.resolve({"operations": ["outline"],
            "processProfiles": {"outline": {"id": saved["id"],
                "fingerprint": saved["fingerprint"]}},
            "material": {"thicknessMm": 1}, "confirmedSetup": True}, {})
        self.assertNotIn("stepDownMm", plan["operationSettings"]["outline"])
        resolved = resolved_outline_settings(
            plan["operationSettings"]["outline"])
        self.assertEqual(resolved["stepDownMm"], .2)
        self.assertEqual(resolved["millPower"], 1000)

    def test_skin_keeps_requested_material_without_using_backing_overrun(self):
        settings = values(millOverrunMm=5, backingMm=0, cuttingLengthMm=0,
                          uncertaintyMm=100)
        checked = validate_tool_values(settings, "outline")
        self.assertNotIn("millOverrunMm", checked)
        operations, programs = self.generate(settings)
        self.assertEqual(operations[0]["depthMm"], .7)
        self.assertEqual(operations[0]["passes"], 4)
        self.assertIn("G1 Z-0.70000 F5", programs["outline.nc"])
        self.assertIn("M3 S1000", programs["outline.nc"])

    def test_tabs_retain_same_thickness_only_at_four_bridges(self):
        operations, programs = self.generate(values("tabs"))
        self.assertEqual(operations[0]["depthMm"], 1.2)
        self.assertEqual(operations[0]["tabWidthMm"], 3)
        self.assertEqual(operations[0]["passes"], 6)
        self.assertEqual(programs["outline.nc"].count("G1 Z-0.70000 F5"), 12)
        self.assertIn("G1 Z-1.20000 F5", programs["outline.nc"])

    def test_through_ignores_remaining_and_requires_workholding(self):
        settings = values("through", remainingMm=5)
        self.assertNotIn("remainingMm", validate_tool_values(
            settings, "outline"))
        with self.assertRaisesRegex(ValueError, "mocowanie"):
            self.generate(settings)
        operations, programs = self.generate(settings, confirmedThroughCut=True)
        self.assertEqual(operations[0]["depthMm"], 1.2)
        self.assertNotIn("G1 Z-0.70000", programs["outline.nc"])

    def test_optional_pass_and_tab_width_overrides_are_used(self):
        operations, _ = self.generate(values("tabs", stepDownMm=.4,
                                              tabWidthMm=4))
        self.assertEqual(operations[0]["passes"], 3)
        self.assertEqual(operations[0]["tabWidthMm"], 4)

    def test_automatic_tab_width_tracks_cutter_radius(self):
        operations, programs = self.generate(values("tabs", millDiameterMm=3))
        self.assertEqual(operations[0]["tabWidthMm"], 5)
        parsed = parse_program("outline.nc", programs["outline.nc"])
        self.assertEqual(parsed["bounds_mm"]["X"], [-1.5, 21.5])

    def test_invalid_overrides_and_retention_thickness_are_rejected(self):
        for change in ({"stepDownMm": 0}, {"stepDownMm": True},
                       {"tabWidthMm": 2, "millDiameterMm": 2},
                       {"remainingMm": 1}, {"millOverrunMm": None}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.generate(values("tabs", **change))

    def test_legacy_profile_preserved_until_reviewed_save(self):
        store = ProcessProfiles(self.root / "profiles.json")
        saved = store.save({"kind": "outline", "name": "Old",
            "values": tool_values("outline"), "confirmedTools": True}, {})
        original = store.filename.read_bytes()
        self.assertIsNone(ProcessProfiles(store.filename).error)
        self.assertEqual(store.filename.read_bytes(), original)
        updated = store.save({"kind": "outline", "name": "New",
            "values": values(), "confirmedTools": True, "id": saved["id"],
            "expectedFingerprint": saved["fingerprint"]}, {})
        self.assertEqual(updated["revision"], 2)
        self.assertNotIn("backingMm", updated["values"])
        with self.assertRaises(ValueError):
            store.assert_snapshot(saved)


if __name__ == "__main__":
    unittest.main()

# ---------------------------------------------------------------------------
# end of file
# ---------------------------------------------------------------------------
