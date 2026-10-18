# ---------------------------------------------------------------------------
# test_surfaces.py
# 2026-10-18
# - Hardware-free grid motion, map validity and compensated stream tests.
# ---------------------------------------------------------------------------
"""Inject serial replies; never open a controller or start a real machine."""

import math
import unittest
from unittest.mock import patch

from monitor.cnc import Controller
from monitor.compensation import compensate_program, height_at, live_offset
from monitor.jobs import WORD, parse_program
from monitor.surfaces import SurfaceScan, plan_grid
from test_probes import Port


PROGRAM = (
    "G21 G90 G94 G54\nG0 Z3\nG0 X0 Y0\nM3 S300\n"
    "G1 Z-0.07 F20\nG1 X10 Y10 F100\nG1 X0 Y10\nG0 Z3\nM5\nM30"
)


class SurfaceTests(unittest.TestCase):
    """Cover reference zero, every waypoint, guards and stream integration."""

    def setUp(self):
        self.cnc = Controller()
        self.port = Port()
        self.cnc.port = self.port
        self.cnc.info = ["$6=1", "$13=0"]
        self.cnc._accept_status("<Idle|MPos:0,0,6|WCO:0,0,5|Pn:P>")
        self.cnc._accept_status("<Idle|MPos:0,0,6|WCO:0,0,5>")
        self.cnc.jobs.load(parse_program("pcb.nc", PROGRAM))
        self.payload = {
            "job_id": self.cnc.jobs.job_id, "confirmed": True,
            "position": [0, 0, 1], "distance": 1, "feed": 20,
            "columns": 3, "rows": 3, "area": {"X": [0, 10], "Y": [0, 10]},
            "clearance": 2, "below": 1,
        }
        self.modal = ["[GC:G0 G54 G21 G90 G94 M5]"]

    def start(self):
        with patch.object(self.cnc, "_status"), patch.object(
            self.cnc, "_line", return_value=self.modal
        ):
            return self.cnc.action("surface_start", self.payload)

    def receive(self, value):
        self.port.receive += value.encode()
        self.cnc.surface.tick(self.cnc)

    def reference(self):
        self.start()
        self.receive("[PRB:0,0,5:1]\nok\n<Idle|MPos:0,0,4.997|Pn:P>\n")
        self.assertIn(b"G10L20P1Z-0.0030\n", self.port.writes)
        self.receive("ok\nok\n<Idle|MPos:0,0,7|WCO:0,0,5>\n")
        self.assertEqual(self.cnc.surface.state, "xy_ack")

    def sample(self, point, height):
        x, y = point["x"], point["y"]
        self.receive(f"ok\n<Idle|MPos:{x},{y},7|WCO:0,0,5>\n")
        self.assertEqual(self.cnc.surface.state, "probing")
        z = 5 + height
        self.receive(f"[PRB:{x},{y},{z}:1]\nok\n"
                     f"<Idle|MPos:{x},{y},{z - 0.002}|Pn:P>\n")
        self.assertEqual(self.cnc.surface.state, "retract_ack")
        self.receive(f"ok\n<Idle|MPos:{x},{y},7|WCO:0,0,5>\n")

    def complete(self):
        self.reference()
        for point in self.cnc.surface.points:
            self.sample(point, 0.01 * point["x"] + 0.02 * point["y"])
        return self.cnc.surface

    def test_entire_grid_zeroes_once_and_lifts_before_xy(self):
        surface = self.complete()
        self.assertTrue(surface.valid)
        self.assertEqual(surface.state, "completed")
        self.assertEqual(len(surface.samples), 9)
        self.assertEqual(surface.offset, [0, 0, 5])
        self.assertEqual(surface.status()["reference_xy"], [0, 0])
        self.assertEqual(surface.job_id, self.cnc.jobs.job_id)
        self.assertEqual(sum(b"G38.2" in v for v in self.port.writes), 10)
        self.assertEqual(sum(b"G10" in v for v in self.port.writes), 1)
        self.assertEqual(sum(b"G0Z2" in v for v in self.port.writes), 10)
        self.assertAlmostEqual(surface.samples[-1]["z"], 0.3)
        self.assertFalse(self.port.closed)
        self.assertFalse(any(b"M3" in v for v in self.port.writes))

    def test_grid_validation_and_file_identity_before_motion(self):
        for change in (
            {"job_id": "old"}, {"columns": 12}, {"rows": 1},
            {"columns": True}, {"area": {"X": [1, 10], "Y": [0, 10]}},
            {"area": {"X": [0, float("nan")], "Y": [0, 10]}},
            {"clearance": 0}, {"below": 3}, {"clearance": 4},
        ):
            with self.subTest(change=change):
                original = self.payload
                self.payload = {**original, **change}
                with self.assertRaises(ValueError):
                    self.start()
                self.payload = original
                self.assertEqual(self.port.writes, [])

    def test_stop_failure_and_partial_map_cannot_be_used(self):
        self.reference()
        self.sample(self.cnc.surface.points[0], 0)
        for action in ("probe_start", "surface_start", "job_start", "zero_xy"):
            with self.assertRaises(ValueError):
                self.cnc.action(action, self.payload)
        self.cnc.action("probe_stop", {})
        self.cnc.surface.tick(self.cnc)
        self.assertFalse(self.cnc.surface.valid)
        self.assertEqual(self.cnc.surface.state, "stopped")
        self.assertTrue(self.port.closed)
        with self.assertRaises(ValueError):
            compensate_program(self.cnc.jobs.program, self.cnc.surface)

    def test_alarm_and_offset_change_abort_without_more_samples(self):
        for reply in ("ALARM:5\n", "<Idle|MPos:0,0,7|WCO:1,0,5>\n"):
            self.setUp()
            self.reference()
            self.receive(reply)
            self.assertEqual(self.cnc.surface.state, "failed")
            self.assertFalse(self.cnc.surface.valid)
            self.assertTrue(self.port.closed)

    def test_completed_map_invalidates_after_offset_or_disconnect(self):
        surface = self.complete()
        self.cnc._accept_status("<Idle|MPos:10,10,7|WCO:0,0,5.1>")
        self.assertFalse(surface.valid)
        surface.valid = True
        self.cnc._close("test")
        self.assertFalse(surface.valid)

    def test_reference_offset_must_match_captured_contact(self):
        self.start()
        self.receive("[PRB:0,0,5:1]\nok\n<Idle|MPos:0,0,4.997|Pn:P>\n")
        self.receive("ok\nok\n<Idle|MPos:0,0,8|WCO:0,0,6>\n")
        self.assertEqual(self.cnc.surface.state, "failed")
        self.assertFalse(self.cnc.surface.valid)
        self.assertFalse(any(b"G1X" in value for value in self.port.writes))
    def test_bilinear_interpolation_and_no_extrapolation(self):
        surface = self.complete()
        for x, y in ((0, 0), (10, 10), (3.2, 7.7), (10, 0), (0, 10)):
            self.assertAlmostEqual(
                height_at(surface, x, y), 0.01 * x + 0.02 * y
            )
        for x, y in ((-1, 0), (11, 0), (0, -1), (0, 11)):
            with self.assertRaises(ValueError):
                height_at(surface, x, y)

    def test_compensation_splits_moves_and_preserves_original(self):
        surface = self.complete()
        original = self.cnc.jobs.program
        before = [line.copy() for line in original["lines"]]
        result = compensate_program(original, surface)
        self.assertGreater(len(result["lines"]), len(original["lines"]))
        self.assertEqual(before, original["lines"])
        self.assertAlmostEqual(result["bounds_mm"]["Z"][1], 3.3)
        points = []
        for line in result["lines"]:
            words = dict(WORD.findall(line["code"]))
            if words.get("G") == "1" and line["source_line"] == 6:
                x, y, z = [float(words[axis]) for axis in "XYZ"]
                self.assertAlmostEqual(z, -0.07 + 0.01 * x + 0.02 * y, places=3)
                points.append((x, y))
        self.assertGreater(len(points), 20)
        for previous, point in zip([(0, 0)] + points, points):
            self.assertLessEqual(math.dist(previous, point), 0.501)

    def test_saddle_height_and_unsafe_rapid_rejected(self):
        surface = self.complete()
        for sample in surface.samples:
            sample["z"] = sample["x"] * sample["y"] * 0.002
        self.assertAlmostEqual(height_at(surface, 3, 7), 0.042)
        bad = parse_program("bad.nc", PROGRAM.replace("G1 Z-0.07", "G0 Z-0.07"))
        with self.assertRaises(ValueError):
            compensate_program(bad, surface)

    def test_live_zero_readback_includes_g92_and_tool_offset(self):
        self.assertEqual(live_offset([
            "[G54:1,2,3]", "[G92:0.1,0.2,0.3]", "[TLO:0.5]",
        ]), [1.1, 2.2, 3.8])
        for replies in ([], ["[G54:0,0,0]"], [
            "[G54:0,0,0]", "[G92:0,0,0]", "[TLO:nan]",
        ]):
            with self.assertRaises(ValueError):
                live_offset(replies)

    def test_job_start_binds_map_and_creates_separate_execution(self):
        surface = self.complete()
        payload = {"confirmed": True, "job_id": self.cnc.jobs.job_id,
                   "surface_map_id": surface.map_id}
        with patch.object(self.cnc, "_status"), patch.object(
            self.cnc, "_line", side_effect=[self.modal, [
                "[G54:0,0,5]", "[G92:0,0,0]", "[TLO:0]",
            ]]
        ):
            self.cnc.action("job_start", payload)
        self.assertTrue(self.cnc.jobs.status()["compensated"])
        self.assertIsNot(self.cnc.jobs.execution, self.cnc.jobs.program)
        self.cnc.jobs.tick(self.cnc)
        self.port.receive += b"ok\n"
        self.cnc.jobs.tick(self.cnc)
        self.assertIn(b"G0Z3.3000\n", self.port.writes)
        with self.assertRaises(RuntimeError):
            self.cnc._accept_status("<Idle|MPos:10,10,7|WCO:0,0,5.1>")

    def test_stale_map_is_rejected_before_job_start(self):
        surface = self.complete()
        payload = {"confirmed": True, "job_id": self.cnc.jobs.job_id,
                   "surface_map_id": surface.map_id}
        with patch.object(self.cnc, "_status"), patch.object(
            self.cnc, "_line", side_effect=[self.modal, [
                "[G54:0,0,6]", "[G92:0,0,0]", "[TLO:0]",
            ]]
        ):
            with self.assertRaises(ValueError):
                self.cnc.action("job_start", payload)
        self.assertFalse(surface.valid)
        self.assertFalse(self.cnc.jobs.active())


if __name__ == "__main__":
    unittest.main()

# ---------------------------------------------------------------------------
# end of file
# ---------------------------------------------------------------------------
