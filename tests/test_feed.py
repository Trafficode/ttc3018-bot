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

from monitor.cnc import Controller
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
        payload = {"job_id": cnc.jobs.job_id, "confirmed": True,
                   "xy_feed": 301}
        with patch.object(cnc, "_status"), patch.object(
            cnc, "_line", return_value=["[GC:G0 G54 G21 G90 G94 M5]"]
        ):
            with self.assertRaises(ValueError):
                cnc.action("job_start", payload)
            self.assertFalse(cnc.jobs.active())
            payload["xy_feed"] = 75
            cnc.action("job_start", payload)
        self.assertEqual(cnc.jobs.status()["xy_feed"], 75)
        self.assertFalse(cnc.jobs.status()["compensated"])
        self.assertEqual(cnc.port.writes, [])

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
