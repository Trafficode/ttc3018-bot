# ---------------------------------------------------------------------------
# test_profiles.py
# 2026-10-24
# - Measured profiles, persistence, path geometry and no-motion interlocks.
# ---------------------------------------------------------------------------
"""All data and serial responses are simulated."""

import json
from pathlib import Path
import tempfile
import subprocess
import sys
import unittest
from unittest.mock import patch

from monitor.calibration import Calibration, coupon, settings, tool_diameter
from monitor.cnc import Controller
from monitor.jobs import parse_program
from monitor.profiles import ProfileStore, fit_profile


CONFIG = {"tip": 0.1, "angle": 30, "feed": 100, "plunge": 20,
          "power": 300, "width": 1, "depth": 0.05}


def trial(index, depth, measured, used=0.2):
    """The actual tool model in this fixture is D = 0.1 + 2*h."""
    return {**CONFIG, "trial_id": str(index), "depth": depth,
            "width": measured - used + 0.1 + 2 * depth,
            "geometry": {"diameter_mm": used},
            "measured_width": measured, "state": "completed"}


class ProfileTests(unittest.TestCase):
    """Calibration evidence must survive restarts and never scale axes."""

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "calibration-profiles.json"
        self.store = ProfileStore(self.path)
        for row in (trial(1, 0.05, 1), trial(2, 0.15, 1, used=0.3)):
            self.store.record(row)
        self.payload = {"name": "V30 · test", "samples": [
            {"trial_id": "1", "measured_width": 1},
            {"trial_id": "2", "measured_width": 1},
        ]}

    def activate(self):
        profile = self.store.create(self.payload)
        self.store.select(profile["id"])
        return profile

    def test_fit_uses_actual_generated_diameter(self):
        profile = self.activate()
        self.assertAlmostEqual(profile["model"]["intercept_mm"], 0.1)
        self.assertAlmostEqual(profile["model"]["slope"], 2)
        self.assertAlmostEqual(profile["model"]["rmse_mm"], 0)
        self.assertEqual(ProfileStore(self.path).active, profile)
        self.assertEqual(len(ProfileStore(self.path).data["trials"]), 2)

    def test_default_is_nominal_and_immutable(self):
        self.assertIsNone(self.store.active["model"])
        self.assertEqual(self.store.resolve(CONFIG, {}), CONFIG)
        self.assertAlmostEqual(tool_diameter(CONFIG, 0.05), 0.126794919243)
        with self.assertRaises(ValueError):
            self.store.delete("default")
        profile = self.store.create(self.payload)
        self.assertEqual(self.store.active["id"], "default")
        self.store.select(profile["id"])
        self.store.delete(profile["id"])
        self.assertEqual(self.store.active["id"], "default")
        self.assertEqual(self.store.data["profiles"], [])

    def test_manual_profile_needs_no_recorded_trials(self):
        self.store.data["trials"] = []
        payload = {**CONFIG, "source": "manual", "name": "Ręczny",
                   "samples": [
                       {"depth": .05, "width": 1.1, "measured_width": 1,
                        "used_diameter": .1},
                       {"depth": .15, "width": 1.3, "measured_width": 1,
                        "used_diameter": .1},
                   ]}
        profile = self.store.create(payload)
        self.assertAlmostEqual(profile["model"]["slope"], 2)
        self.assertAlmostEqual(profile["model"]["intercept_mm"], .1)
        self.assertEqual(profile["observations"][0]["source"], "manual")
        self.assertEqual(self.store.data["trials"], [])
        self.assertEqual(self.store.active["id"], "default")
        self.assertEqual(ProfileStore(self.path).data["profiles"][0], profile)
        for key, value in (("tip", None), ("angle", 100), ("feed", 0)):
            with self.assertRaises(ValueError):
                self.store.create({**payload, key: value})
        for key, value in (("depth", ""), ("width", None),
                           ("used_diameter", float("nan")),
                           ("measured_width", 0)):
            rows = [payload["samples"][0], {**payload["samples"][1],
                                           key: value}]
            with self.assertRaises(ValueError):
                self.store.create({**payload, "samples": rows})

    def test_edit_keeps_one_list_entry_and_rejects_stale_cam(self):
        original = self.activate()
        updated = self.store.update({**self.payload, "profile_id":original["id"],
                                    "profile_fingerprint":original["fingerprint"],
                                    "name":"Nowe ustawienia", "depth":.1})
        self.assertEqual(updated["id"], original["id"])
        self.assertNotEqual(updated["fingerprint"], original["fingerprint"])
        self.assertEqual(len(self.store.data["profiles"]), 1)
        self.assertEqual(self.store.data["revisions"][0], original)
        self.assertNotIn("revisions", self.store.status())
        self.assertEqual(ProfileStore(self.path).active, updated)
        program = coupon([0,0],CONFIG)
        program["cam_profile"] = {"id":original["id"],
                                  "fingerprint":original["fingerprint"]}
        with self.assertRaises(ValueError):
            self.store.check_program(program,{})
        with self.assertRaises(ValueError):
            self.store.update({**self.payload,"profile_id":original["id"],
                               "profile_fingerprint":original["fingerprint"]})

    def test_manual_nominal_diameter_matches_the_default_generator(self):
        profile = self.store.create({**CONFIG, "source": "manual",
                                    "name": "Nominalny", "samples": [
            {"depth": .05, "width": 1, "measured_width": 1},
            {"depth": .15, "width": 1, "measured_width": 1},
        ]})
        for row in profile["observations"]:
            self.assertAlmostEqual(row["geometry"]["diameter_mm"],
                                   tool_diameter(CONFIG, row["depth"]))

    def test_confirmed_delete_active_invalidates_test_and_file_maps(self):
        cnc = Controller(profile_path=self.path.with_name("preset.json"))
        profile = cnc.calibration.profiles.create(self.payload)
        cnc.action("profile_select", {"profile_id": profile["id"]})
        cnc.surface.map_id, cnc.surface.valid = "file", True
        cnc.calibration.mode = "profile_test"
        cnc.calibration.scan.map_id, cnc.calibration.scan.valid = "test", True
        payload = {"profile_id":profile["id"],
                   "profile_fingerprint":profile["fingerprint"]}
        with self.assertRaises(ValueError):
            cnc.action("profile_delete", payload)
        cnc.action("profile_delete", {**payload,"confirmed":True})
        self.assertEqual(cnc.calibration.profiles.active["id"], "default")
        self.assertFalse(cnc.surface.valid)
        self.assertFalse(cnc.calibration.scan.valid)

    def test_one_measurement_preserves_tool_angle_and_offsets_diameter(self):
        profile = self.store.create({**CONFIG, "source": "manual",
                                    "name": "Jeden pomiar", "samples": [
            {"depth": .05, "width": .7, "measured_width": .5},
        ]})
        model = profile["model"]
        self.assertEqual(model["kind"], "single_offset")
        self.assertAlmostEqual(model["offset_mm"], .2)
        self.assertIsNone(model["rmse_mm"])
        self.store.select(profile["id"])
        for depth in (.03, .05, .1, .2):
            config = {**CONFIG, "depth": depth, "_calibration": profile}
            self.assertAlmostEqual(tool_diameter(config, depth),
                                   tool_diameter(CONFIG, depth) + .2)
            self.assertAlmostEqual(coupon([0, 0], config)["tool_geometry"][
                "strip_width_mm"], CONFIG["width"])
        self.assertEqual(ProfileStore(self.path).active, profile)

    def test_one_recorded_trial_can_create_a_profile(self):
        profile = self.store.create({"name": "Z jednej próby", "samples": [
            {"trial_id": "1", "measured_width": 1},
        ]})
        self.assertEqual(len(profile["observations"]), 1)
        self.assertEqual(profile["model"]["kind"], "single_offset")

    def test_one_point_cannot_generate_negative_diameters(self):
        profile = self.store.create({**CONFIG, "depth": .3, "source": "manual",
                                    "name": "Ujemna korekta", "samples": [
            {"depth": .3, "width": .5, "measured_width": .65},
        ]})
        self.store.select(profile["id"])
        with self.assertRaises(ValueError):
            self.store.resolve({**CONFIG, "depth": .01}, {
                "profile_id": profile["id"],
                "profile_fingerprint": profile["fingerprint"],
            })

    def test_custom_profile_controls_generated_strip_at_each_depth(self):
        profile = self.activate()
        payload = {"profile_id": profile["id"],
                   "profile_fingerprint": profile["fingerprint"]}
        for depth in (0.05, 0.1, 0.15):
            config = {**CONFIG, "depth": depth, "_calibration": profile}
            program = coupon([0, 0], config)
            geometry = program["tool_geometry"]
            self.assertAlmostEqual(geometry["diameter_mm"], 0.1 + 2 * depth)
            self.assertAlmostEqual(geometry["centreline_spacing_mm"]
                                   - geometry["diameter_mm"], 1)
            self.assertEqual(geometry["profile_id"], profile["id"])
        for change in ({"depth": 0.16}, {"feed": 75}, {"tip": 0.2}):
            with self.assertRaises(ValueError):
                self.store.resolve({**CONFIG, **change}, payload)
        with self.assertRaises(ValueError):
            self.store.resolve(CONFIG, {})

    def test_reject_bad_evidence(self):
        for samples in ([self.payload["samples"][0]] * 2,
                        [{"trial_id": "invented", "measured_width": 1}] * 2):
            with self.assertRaises(ValueError):
                self.store.create({**self.payload, "samples": samples})
        rows = [trial(1, 0.05, 1), trial(2, 0.05, 1)]
        with self.assertRaises(ValueError):
            fit_profile(rows)
        rows[1] = trial(2, 0.15, 1)
        for key, value in (("feed", 75), ("measured_width", float("nan"))):
            with self.assertRaises(ValueError):
                fit_profile([rows[0], {**rows[1], key: value}])

    def test_corruption_blocks_execution_and_preserves_file(self):
        profile = self.activate()
        text = self.path.read_text(encoding="utf-8")
        data = json.loads(text)
        data["profiles"][0]["model"]["slope"] = 9
        self.path.write_text(json.dumps(data), encoding="utf-8")
        before = self.path.read_bytes()
        broken = ProfileStore(self.path)
        self.assertTrue(broken.error)
        with self.assertRaises(ValueError):
            broken.resolve(CONFIG, {})
        with self.assertRaises(ValueError):
            broken.select(profile["id"])
        self.assertEqual(self.path.read_bytes(), before)

    def test_cam_identity_and_overrides(self):
        program = coupon([0, 0], CONFIG)
        self.store.check_program(program, {})
        profile = self.activate()
        with self.assertRaises(ValueError):
            self.store.check_program(program, {})
        marker = {"id": profile["id"],
                  "fingerprint": profile["fingerprint"]}
        program["cam_profile"] = marker
        self.store.check_program(program, {})
        for payload in ({"service_depth": True}, {"xy_feed": 100}):
            with self.assertRaises(ValueError):
                self.store.check_program(program, payload)
        self.store.select("default")
        with self.assertRaises(ValueError):
            self.store.check_program(program, {})
        content = "\n".join(row["code"] for row in program["lines"])
        header = (f"; BARK_BEETLE_PROFILE {marker['id']} "
                  f"{marker['fingerprint']}\n")
        self.assertEqual(parse_program("test.nc", header + content)[
            "cam_profile"], marker)
        for invalid in (header + header + content, content + "\n" + header):
            with self.assertRaises(ValueError):
                parse_program("test.nc", invalid)

    def test_selection_never_opens_usb_and_invalidates_maps(self):
        cnc = Controller()
        cnc.calibration = Calibration(self.path.with_name("preset.json"))
        profile = cnc.calibration.profiles.create(self.payload)
        cnc.surface.valid = True
        cnc.surface.map_id = "file-map"
        cnc.calibration.scan.valid = True
        cnc.calibration.scan.map_id = "service-map"
        with patch.object(cnc, "_status") as status:
            cnc.action("profile_select", {"profile_id": profile["id"]})
            status.assert_not_called()
        self.assertFalse(cnc.surface.valid)
        self.assertTrue(cnc.calibration.scan.valid)
        cnc.calibration.mode = "profile_test"
        cnc.action("profile_select", {"profile_id": "default"})
        self.assertFalse(cnc.calibration.scan.valid)
        self.assertIsNone(cnc.port)
        cnc.jobs.state = "running"
        with self.assertRaises(ValueError):
            cnc.action("profile_select", {"profile_id": "default"})
        cnc.jobs.state = "empty"
        cnc.port = object()
        cnc.report = {"state": "Jog"}
        with patch.object(cnc, "_status"), self.assertRaises(ValueError):
            cnc.action("profile_select", {"profile_id": "default"})

    def test_pc_helper_exports_and_tags_without_rewriting_paths(self):
        profile = self.activate()
        export = self.path.with_name("export.json")
        export.write_text(json.dumps({"version": 1, "profile": profile}),
                          encoding="utf-8")
        script = Path(__file__).resolve().parents[1] / (
            "scripts/calibration_cam.py"
        )
        result = subprocess.run(
            [sys.executable, str(script), str(export)],
            check=True, capture_output=True, text=True,
        )
        self.assertAlmostEqual(json.loads(result.stdout)[
            "tool_diameter_mm"], 0.2)
        program = coupon([0, 0], CONFIG)
        original = "\n".join(row["code"] for row in program["lines"])
        source = self.path.with_name("source.nc")
        output = self.path.with_name("tagged.nc")
        source.write_text(original, encoding="ascii")
        command = [sys.executable, str(script), str(export), "--tag",
                   str(source), "--output", str(output)]
        self.assertNotEqual(subprocess.run(
            command, capture_output=True
        ).returncode, 0)
        self.assertFalse(output.exists())
        subprocess.run(command + ["--confirm-cam-profile"], check=True,
                       capture_output=True)
        self.assertEqual(output.read_text(encoding="ascii").split("\n", 1)[1],
                         original)
        self.assertEqual(source.read_text(encoding="ascii"), original)

# ---------------------------------------------------------------------------
# end of file
# ---------------------------------------------------------------------------
