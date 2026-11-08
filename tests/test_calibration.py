# ---------------------------------------------------------------------------
# test_calibration.py
# 2026-10-24
# - Simulated five-point probing, depth-only geometry and guarded cutting.
# ---------------------------------------------------------------------------
"""Use a fake serial port; no physical CNC access."""

import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

from monitor.calibration import (
    Calibration, coupon, five_height, settings, tool_diameter, with_cut_depth,
)
from monitor.cnc import Controller
from monitor.compensation import compensate_program
from monitor.jobs import WORD, parse_program
from test_probes import Port


MODAL = ["[GC:G0 G54 G21 G90 G94 M5]"]
OFFSET = ["[G54:10,20,5]", "[G92:0,0,0]", "[TLO:0]"]


class CalibrationTests(unittest.TestCase):
    """Check the complete motion protocol and interlocks, not just helpers."""

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.cnc = Controller()
        self.cnc.calibration = Calibration(
            Path(self.directory.name) / "profile.json"
        )
        self.port = Port()
        self.cnc.port = self.port
        self.cnc.info = ["$6=1", "$13=0"]
        self.cnc._accept_status("<Idle|MPos:12,23,6|WCO:10,20,5|Pn:P>")
        self.cnc._accept_status("<Idle|MPos:12,23,6|WCO:10,20,5>")
        self.config = {"depth": 0.05, "width": 0.5,
                       "feed": 100, "plunge": 20, "power": 300,
                       "tip": 0.1, "angle": 30}

    def start(self, **extra):
        payload = {**self.config, "confirmed": True,
                   "position": self.cnc.report["position"][:],
                   "session": self.cnc.calibration.session, **extra}
        with patch.object(self.cnc, "_status"), patch.object(
            self.cnc, "_line", return_value=MODAL
        ):
            return self.cnc.action("service_prepare", payload)

    def receive(self, text):
        self.port.receive += text.encode()
        self.cnc.last_probe.tick(self.cnc)

    def complete(self):
        self.start()
        self.receive("ok\n<Idle|MPos:12,23,6|WCO:10,20,5>\n")
        scan = self.cnc.calibration.scan
        for point in scan.points:
            x, y = point["x"], point["y"]
            self.receive(f"ok\n<Idle|MPos:{x+10},{y+20},6>\n")
            self.assertEqual(scan.state, "probing")
            height = 0.01 * (x - 2) + 0.02 * (y - 3)
            z = 5 + height
            self.receive(f"[PRB:{x+10},{y+20},{z}:1]\nok\n"
                         f"<Idle|MPos:{x+10},{y+20},{z-.002}|Pn:P>\n")
            self.receive(f"ok\n<Idle|MPos:{x+10},{y+20},6>\n")
        self.assertTrue(scan.valid)
        return scan

    def cut(self, **extra):
        service = self.cnc.calibration
        payload = {**self.config, "confirmed": True, "clip_removed": True,
                   "position": self.cnc.report["position"][:],
                   "session": service.session, "map_id": service.scan.map_id,
                   **extra}

        def reply(command):
            return OFFSET if command == "$#" else MODAL

        with patch.object(self.cnc, "_status"), patch.object(
            self.cnc, "_line", side_effect=reply
        ):
            return self.cnc.action("service_cut", payload)

    def test_exactly_five_touches_preserve_all_work_offsets(self):
        scan = self.complete()
        self.assertEqual(len(scan.samples), 5)
        self.assertEqual(scan.offset, [10, 20, 5])
        self.assertEqual(self.cnc.offset, [10, 20, 5])
        self.assertEqual(sum(b"G38.2" in v for v in self.port.writes), 5)
        self.assertEqual(sum(b"G90G38.2Z-0.4000F20" in v
                             for v in self.port.writes), 5)
        self.assertFalse(any(b"G10" in v or b"M3" in v
                             for v in self.port.writes))
        self.assertEqual(scan.samples[4]["x"], 8)
        self.assertAlmostEqual(scan.samples[4]["z"], 0.11)

    def test_service_is_independent_of_selected_profile(self):
        store = self.cnc.calibration.profiles
        for index, depth, width in ((1, .05, 1.1), (2, .15, 1.3)):
            store.record({**self.config, "trial_id": str(index),
                          "state": "completed", "depth": depth,
                          "width": width,
                          "geometry": {"diameter_mm": .1}})
        profile = store.create({"name": "Test", "samples": [
            {"trial_id": "1", "measured_width": 1},
            {"trial_id": "2", "measured_width": 1},
        ]})
        with patch.object(self.cnc, "_status"):
            self.cnc.action("profile_select", {"profile_id": profile["id"]})
        self.config.update(depth=.1, profile_id=profile["id"],
                           profile_fingerprint=profile["fingerprint"])
        self.complete()
        self.cut()
        service = self.cnc.calibration
        geometry = service.runner.program["tool_geometry"]
        nominal = tool_diameter(self.config, .1)
        self.assertAlmostEqual(geometry["diameter_mm"], nominal)
        self.assertAlmostEqual(geometry["centreline_spacing_mm"], .5 + nominal)
        self.assertEqual(geometry["profile_id"], "default")
        service.runner.state = "completed"
        service.observe()
        self.assertEqual(len(store.data["trials"]), 3)
        latest = store.data["trials"][-1]
        self.assertAlmostEqual(latest["geometry"]["diameter_mm"], nominal)
        self.assertEqual(latest["depth"], .1)
        self.assertEqual(latest["feed"], self.config["feed"])

    def test_centre_affects_interpolation_no_extrapolation(self):
        scan = self.complete()
        scan.samples[4]["z"] = 0.3
        self.assertAlmostEqual(five_height(scan, 8, 5.5), 0.3)
        for point in scan.samples:
            self.assertAlmostEqual(five_height(scan, point["x"], point["y"]),
                                   point["z"])
        with self.assertRaises(ValueError):
            five_height(scan, 15, 5)

    def test_emitted_contour_preserves_strip_width_and_length_at_each_depth(self):
        for tip, angle in ((.1, 30), (.2, 60)):
            for depth in (.025, .05, .1, .2, .3):
                for width in (.2, .5, 1):
                    config = {**self.config, "tip": tip, "angle": angle,
                              "depth": depth, "width": width}
                    program = coupon([2, 3], config)
                    diameter = tool_diameter(config, depth)
                    ys = [float(dict(WORD.findall(line["code"]))["Y"])
                          for line in program["lines"]
                          if line["code"].startswith("G1Y")]
                    xs = [float(dict(WORD.findall(line["code"]))["X"])
                          for line in program["lines"]
                          if line["code"].startswith("G1X")]
                    self.assertAlmostEqual(max(ys) - min(ys) - diameter,
                                           width, delta=.00011)
                    self.assertAlmostEqual(max(xs) - min(xs) - diameter,
                                           10, delta=.00011)

    def test_current_payload_drives_compensated_job_not_scan_settings(self):
        self.complete()
        self.cut(depth=.1, width=.7, feed=75, plunge=12, power=700)
        service = self.cnc.calibration
        program = service.runner.program
        self.assertEqual(service.config, {**self.config, "depth": .1,
                         "width": .7, "feed": 75, "plunge": 12,
                         "power": 700})
        self.assertEqual(program["max_feed"], 75)
        self.assertEqual(program["max_power"], 700)
        self.assertTrue(program["compensated"])
        self.assertIsNone(program["tool_geometry"]["correction"])
        self.assertAlmostEqual(
            program["tool_geometry"]["centreline_spacing_mm"]
            - program["tool_geometry"]["diameter_mm"], .7,
        )
        self.assertEqual(service.pending["geometry"],
                         program["tool_geometry"])
        points = []
        for line in program["lines"]:
            words = dict(WORD.findall(line["code"]))
            if words.get("G") == "1":
                x, y, z = [float(words[axis]) for axis in "XYZ"]
                local_depth = z - .01 * (x - 2) - .02 * (y - 3)
                if abs(local_depth + .1) < .0002 and y > 5:
                    points.append(y)
        self.assertAlmostEqual(max(points) - min(points)
                               - tool_diameter(service.config, .1),
                               .7, delta=.0002)

    def test_cut_requires_clip_confirmation_and_consumes_map_once(self):
        self.complete()
        with self.assertRaises(ValueError):
            self.cut(clip_removed=False)
        self.assertFalse(self.cnc.calibration.runner.active())
        original = coupon([0, 0], self.config)
        self.cnc.jobs.load(original)
        self.cut()
        self.assertIs(self.cnc.jobs.program, original)
        self.assertTrue(self.cnc.calibration.runner.active())
        self.assertFalse(self.cnc.calibration.scan.valid)
        for action in ("service_cut", "jog", "probe_start", "job_start"):
            with self.assertRaises(ValueError):
                self.cnc.action(action, {})

    def test_stale_map_offset_or_tool_cannot_start_spindle(self):
        self.complete()
        for extra in ({"map_id": "old"}, {"tip": 0.2},
                      {"position": [99, 3, 2]}):
            with self.assertRaises(ValueError):
                self.cut(**extra)
        self.assertFalse(self.cnc.calibration.runner.active())
        self.cnc.calibration.scan.offset[2] = 6
        with self.assertRaises(ValueError):
            self.cut()
        self.assertFalse(self.cnc.calibration.scan.valid)

    def test_probe_timeout_and_alarm_do_not_zero_or_cut(self):
        for reply in ("ALARM:5\n", "error:5\n"):
            self.setUp()
            self.start()
            self.receive(reply)
            self.assertTrue(self.port.closed)
            self.assertFalse(self.cnc.calibration.scan.valid)
            self.assertFalse(any(b"G10" in v or b"M3" in v
                                 for v in self.port.writes))

    def test_next_field_moves_positive_y_even_after_aborted_trial(self):
        self.complete()
        self.start()
        self.assertEqual(self.cnc.calibration.origin, [2, 9.5])
        self.assertEqual(self.cnc.calibration.scan.area["Y"], [9.5, 14.5])

    def test_profile_saves_only_completed_trial_and_survives_restart(self):
        self.complete()
        self.cut()
        service = self.cnc.calibration
        with self.assertRaises(ValueError):
            service.save({"number": 1, "session": service.session})
        service.runner.state = "completed"
        service.observe()
        service.save({"number": 1, "session": service.session})
        restored = Calibration(service.profile_path)
        self.assertEqual(restored.profile, self.config)
        self.assertEqual(json.loads(service.profile_path.read_text()),
                         self.config)

    def test_bounded_depth_and_probe_heartbeat_expiry(self):
        for depth in (0, -1, 0.31, float("nan"), True):
            with self.assertRaises(ValueError):
                self.start(depth=depth)
        self.start()
        self.cnc.calibration.scan.heartbeat_at = time.monotonic() - 10
        self.receive("")
        self.assertTrue(self.port.closed)
        self.assertFalse(self.cnc.calibration.scan.valid)

    def test_saved_depth_leaves_xy_and_upload_untouched_rejects_multilevel(self):
        original = coupon([0, 0], self.config)
        adjusted = with_cut_depth(original, 0.09)
        self.assertTrue(any("Z-0.0500" in v["code"]
                            for v in original["lines"]))
        self.assertTrue(any("Z-0.0900" in v["code"]
                            for v in adjusted["lines"]))
        self.assertEqual(
            [v["code"] for v in original["lines"] if "X" in v["code"]],
            [v["code"] for v in adjusted["lines"] if "X" in v["code"]],
        )
        for content in (
            "G1Z-0.05F20\nG1Z-0.07", "G1X1Y1Z-0.05F20"
        ):
            source = ("G21G90G94G54\nG0Z2\nG0X0Y0\n" + content
                      + "\nG0Z2\nM5\nM30")
            with self.assertRaises(ValueError):
                with_cut_depth(parse_program("pcb.nc", source), 0.1)

    def test_profile_is_opt_in_on_production_execution(self):
        original = coupon([0, 0], self.config)
        self.cnc.jobs.load(original)
        self.cnc.calibration.profile = {**self.config, "depth": 0.09}
        with patch.object(self.cnc, "_status"), patch.object(
            self.cnc, "_line", return_value=MODAL
        ):
            with self.assertRaises(ValueError):
                self.cnc.action("job_start", {
                    "job_id": self.cnc.jobs.job_id, "confirmed": True,
                    "service_depth": True, "expected_depth": 0.08,
                })
            self.cnc.action("job_start", {
                "job_id": self.cnc.jobs.job_id, "confirmed": True,
                "service_depth": True, "expected_depth": 0.09,
                "xy_feed": 75,
            })
        self.assertIs(self.cnc.jobs.program, original)
        execution = self.cnc.jobs.execution
        self.assertTrue(any("Z-0.0900" in v["code"]
                            for v in execution["lines"]))

    def test_speeds_can_change_after_mapping_without_moving_xy(self):
        self.complete()
        self.cut(feed=75, plunge=12, power=700)
        service = self.cnc.calibration
        self.assertEqual(service.pending["plunge"], 12)
        lines = [item["code"] for item in service.runner.program["lines"]]
        self.assertIn("M3S700", lines)
        self.assertTrue(any("F12" in code and "G1" in code
                            for code in lines))
        self.assertTrue(any("F75" in code and "G1" in code
                            for code in lines))
        service.runner.state = "completed"
        service.observe()
        service.save({"number": 1, "session": service.session})
        self.assertEqual(service.profile["plunge"], 12)
        self.start(feed=50, plunge=8, power=600)
        self.assertEqual(service.origin, [2, 9.5])

    def test_speed_limits_and_legacy_profile(self):
        self.complete()
        for changes in ({"plunge": 0}, {"plunge": 101},
                        {"plunge": True}, {"feed": 301}, {"power": 1001}):
            with self.assertRaises(ValueError):
                self.cut(**changes)
        legacy = {key: value for key, value in self.config.items()
                  if key != "plunge"}
        path = Path(self.directory.name) / "legacy.json"
        path.write_text(json.dumps(legacy))
        self.assertEqual(Calibration(path).profile["plunge"], 20)

    def test_strip_width_can_change_after_map_and_tool_is_saved(self):
        self.complete()
        self.cut(width=0.9)
        service = self.cnc.calibration
        self.assertEqual(service.pending["width"], 0.9)
        self.assertEqual(service.pending["tip"], 0.1)
        self.assertEqual(service.pending["angle"], 30)
        service.runner.state = "completed"
        service.observe()
        service.save({"number": 1, "session": service.session})
        self.assertEqual(Calibration(service.profile_path).profile["width"], .9)
        self.start(width=1.1, tip=.2, angle=60)
        self.assertEqual(service.config["tip"], .2)

    def test_tool_formula_bounds_and_legacy_defaults(self):
        self.assertAlmostEqual(tool_diameter(self.config, .05), .126794919)
        self.assertAlmostEqual(tool_diameter({"tip": .1, "angle": 60}, .1),
                               .2154700538)
        for extra in ({"tip": 0}, {"tip": True}, {"angle": 91},
                      {"angle": float("nan")}, {"width": 2.1}):
            with self.assertRaises(ValueError):
                self.start(**extra)
        with self.assertRaises(ValueError):
            self.start(width=2, tip=.5, angle=90, depth=.3)
        old = {key: value for key, value in self.config.items()
               if key not in ("tip", "angle", "plunge")}
        self.assertEqual(settings(old)["tip"], .1)
        self.assertEqual(settings(old)["angle"], 30)


if __name__ == "__main__":
    unittest.main()

# ---------------------------------------------------------------------------
# end of file
# ---------------------------------------------------------------------------
