# ---------------------------------------------------------------------------
# test_feed.py
# 2026-10-19
# - Hardware-free feed selection, modal restoration and compensation checks.
# ---------------------------------------------------------------------------
"""Verify execution copies while preserving original geometry and Z feeds."""

import copy
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from controller_fixture import Controller
from monitor.compensation import compensate_program
from monitor.feed import with_xy_feed
from monitor.jobs import JobRunner, WORD, parse_program
from test_probes import Port


PROGRAM = (
    "G21 G90 G94 G54\nM5\nG0 Z3\nG0 X0 Y0\nM3 S300\n"
    "G1 Z-0.05 F30\nG1 X5 F100\nG1 Z-0.1\nF80\n"
    "G1 Y5\nG1 X6 Z-0.2 F25\nG1 X7\nG0 Z3\nM5\nM30"
)


class FeedTests(unittest.TestCase):
    """Exercise modal changes that a simple F replacement would corrupt."""

    def test_controller_selects_feed_and_rejects_invalid_start(self):
        cnc = Controller()
        cnc.port = Port()
        cnc._accept_status("<Idle|MPos:0,0,3|WCO:0,0,0>")
        cnc.jobs.load(parse_program("sample.nc", PROGRAM))
        old = cnc.probe_settings.status()
        saved = cnc.action("probe_settings_save", {
            **old, "travel_clearance_mm": 4.5, "xy_feed_mm_min": 85,
        })
        payload = {"job_id": cnc.jobs.job_id, "confirmed": True,
                   "xy_feed": 301}
        with patch.object(cnc, "_status"), patch.object(
            cnc, "_line", return_value=["[GC:G0 G54 G21 G90 G94 M5]"]
        ):
            with self.assertRaises(ValueError):
                cnc.action("job_start", payload)
            self.assertFalse(cnc.jobs.active())
            payload["xy_feed"] = 75
            with self.assertRaisesRegex(ValueError, "potwierdź ponownie"):
                cnc.action("job_start", {**payload, "probe_settings_revision": old["revision"]})
            cnc.action("job_start", {**payload, "probe_settings_revision": saved["revision"]})
        self.assertEqual(cnc.jobs.status()["xy_feed"], 75)
        self.assertFalse(cnc.jobs.status()["compensated"])
        self.assertEqual(cnc.port.writes, [])
        commands = [row["code"] for row in cnc.jobs.execution["lines"]]
        self.assertIn("G0Z4.5000", commands)
        self.assertIn("G1X0Y0F85", commands)
        self.assertIn("F75G1X5", commands)

    def test_imported_travel_keeps_higher_clearance_and_restores_modal_ramp_feed(self):
        source = parse_program("travel.nc", "\n".join([
            "G21 G90 G94 G54", "M5", "G0 Z1", "G0 X0 Y0", "M3 S300",
            "G1 Z-0.1 F20", "G1 X1 F40", "G0 X2 Y1 Z1",
            "G1 X3 F90", "G1 X4 Z-0.1", "X5",
            "G0 Z6", "X6 Y2 Z1", "M5", "M30",
        ]))
        before = copy.deepcopy(source)
        work = compensate_program(
            source, None, travel={"travel_clearance_mm": 3, "xy_feed_mm_min": 72},
            preserve_clearance=True,
        )
        commands = [line["code"] for line in work["lines"]]
        self.assertEqual(commands[2:9], [
            "G0Z3.0000", "G1X0Y0F72", "M3S300", "F20G1Z-0.1",
            "F40G1X1", "G0Z3.0000", "G1X2Y1F72",
        ])
        self.assertEqual(commands[9:15], [
            "G1X3F72", "G0Z1.0000", "F90G1X4Z-0.1", "G1X5",
            "G0Z6.0000", "G1X6Y2F72",
        ])
        self.assertEqual(source, before)
        self.assertEqual(work["lines"][7]["source_line"], work["lines"][8]["source_line"])

    def test_rapid_xy_that_stays_below_surface_is_rejected_before_execution(self):
        source = parse_program("low.nc", PROGRAM.replace("G1 X5 F100", "G0 X5"))
        with self.assertRaisesRegex(ValueError, "przed przejazdem XY podnieś Z"):
            compensate_program(source, None, travel={
                "travel_clearance_mm": 3, "xy_feed_mm_min": 85,
            }, preserve_clearance=True)

    def test_modal_feed_restored_for_z_and_ramps(self):
        original = parse_program("sample.nc", PROGRAM)
        before = copy.deepcopy(original)
        result = with_xy_feed(original, 75)
        commands = [line["code"] for line in result["lines"]]
        self.assertIn("G1X5F75", commands)
        self.assertIn("G1Z-0.1F100", commands)
        self.assertIn("G1Y5F75", commands)
        self.assertIn("G1X6Z-0.2F25", commands)
        self.assertIn("G1X7F75", commands)
        self.assertEqual(original, before)
        self.assertEqual(result["bounds_mm"], original["bounds_mm"])
        self.assertEqual(result["z_feeds"], [30, 100])
        self.assertEqual([line["source_line"] for line in result["lines"]],
                         [line["source_line"] for line in original["lines"]])
        for old, new in zip(original["lines"], result["lines"]):
            self.assertEqual(
                [(k, v) for k, v in WORD.findall(old["code"]) if k != "F"],
                [(k, v) for k, v in WORD.findall(new["code"]) if k != "F"],
            )

    def test_limits_and_status_do_not_claim_compensation(self):
        program = parse_program("sample.nc", PROGRAM)
        cancelled = parse_program(
            "cancelled.nc", PROGRAM.replace("G1 Z-0.1", "G80\nZ-0.1")
        )
        with self.assertRaises(ValueError):
            with_xy_feed(cancelled, 75)
        for invalid in (None, True, "75", 0, 301, float("nan")):
            with self.subTest(value=invalid), self.assertRaises(ValueError):
                with_xy_feed(program, invalid)
        for value in (1, 75, 300):
            runner = JobRunner()
            runner.load(program)
            runner.start(runner.job_id, with_xy_feed(program, value))
            self.assertEqual(runner.status()["xy_feed"], value)
            self.assertFalse(runner.status()["compensated"])

    def test_feed_is_applied_before_height_segmentation(self):
        program = with_xy_feed(parse_program("sample.nc", PROGRAM), 75)
        surface = SimpleNamespace(
            valid=True, columns=2, rows=2, area={"X": [0, 7], "Y": [0, 5]},
            points=[{}, {}, {}, {}], samples=[
                {"z": 0}, {"z": 0.07}, {"z": 0.12}, {"z": 0.05},
            ],
        )
        execution = compensate_program(program, surface)
        self.assertTrue(execution["compensated"])
        self.assertEqual(execution["xy_feed"], 75)
        current_feed = None
        for line in execution["lines"]:
            values = dict(WORD.findall(line["code"]))
            if "F" in values:
                current_feed = float(values["F"])
            if line["source_line"] in (7, 10, 12):
                self.assertEqual(current_feed, 75)
            if line["source_line"] == 8:
                self.assertEqual(current_feed, 100)
            if line["source_line"] == 11:
                self.assertEqual(current_feed, 25)


if __name__ == "__main__":
    unittest.main()

# ---------------------------------------------------------------------------
# end of file
# ---------------------------------------------------------------------------
