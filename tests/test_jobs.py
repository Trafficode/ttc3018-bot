# ---------------------------------------------------------------------------
# test_jobs.py
# 2026-10-12
# - Hardware-free file validation, serial streaming and operator-state tests.
# ---------------------------------------------------------------------------
"""Exercise the job sender with an in-memory port, never a CNC controller."""

import time
import unittest
from unittest.mock import patch

from monitor.cnc import Controller
from monitor.jobs import parse_program


PROGRAM = "G21 G90 G94 G54\nG0 Z3\nG0 X0 Y0\nF100\nS300\nM3\nG1 X1\nM5\nM30"


class StreamPort:
    """Byte-level fake with independently injected status and ACKs."""

    def __init__(self):
        self.receive = b""
        self.writes = []
        self.closed = False

    @property
    def in_waiting(self):
        return len(self.receive)

    def read(self, count):
        data = self.receive[:count]
        self.receive = self.receive[count:]
        return data

    def write(self, data):
        self.writes.append(data)

    def close(self):
        self.closed = True


class ProgramTests(unittest.TestCase):
    """Validate files before any USB connection or command is possible."""

    def test_valid_program_bounds_and_comments(self):
        program = parse_program("../sample.nc", PROGRAM)
        self.assertEqual(program["name"], "sample.nc")
        self.assertEqual(program["bounds_mm"]["X"], [0, 1])
        self.assertEqual(program["max_feed"], 100)
        self.assertEqual(program["max_power"], 300)
        same = parse_program("sample.nc", "(hello)\n%\nN1 " + PROGRAM)
        self.assertEqual(same["lines"][0]["code"], "G21G90G94G54")

    def test_unsafe_or_unsupported_commands_rejected(self):
        for forbidden in (
            "$H", "$X", "G53G0X0", "G92X0", "G91", "G20", "G81Z-1",
            "M6", "M4", "G38.2Z-1", "G2X1Y1I1J0", "X1e2", "!",
            "S12000", "F1000", "T1", "G1XNaN", "G1X1\x18",
        ):
            with self.subTest(command=forbidden):
                with self.assertRaises(ValueError):
                    parse_program("bad.nc", PROGRAM.replace("F100", forbidden))

    def test_modes_safe_first_move_and_end_required(self):
        for content in (
            PROGRAM.replace("G21 ", ""),
            PROGRAM.replace("G0 Z3", "G0 X1 Y1"),
            PROGRAM.replace("G0 Z3", "G0 Z-1"),
            PROGRAM.replace("G0 X0 Y0", "G0 X0"),
            PROGRAM.replace("M5\n", ""),
            PROGRAM + "\nG0X0Y0", PROGRAM.replace("G1 X1", "G1 X301"),
            PROGRAM.replace("G1 X1", "G1Y181"),
        ):
            with self.subTest(content=content):
                with self.assertRaises(ValueError):
                    parse_program("bad.nc", content)

    def test_upload_limits_and_malformed_comments(self):
        for name, content in (
            ("sample.txt", PROGRAM), ("sample.nc", "(unclosed\n" + PROGRAM),
            ("sample.nc", ";" + "a" * (1024 * 1024)),
            ("sample.nc", PROGRAM.replace("F100", "F100" + " " * 2 + "F1")),
        ):
            with self.assertRaises(ValueError):
                parse_program(name, content)

    def test_load_without_usb_and_start_confirmation(self):
        cnc = Controller()
        cnc.action("job_load", {"name": "sample.nc", "content": PROGRAM})
        self.assertIsNone(cnc.port)
        self.assertEqual(cnc.status()["job"]["state"], "ready")
        with self.assertRaises(ValueError):
            cnc.action("job_start", {"job_id": cnc.jobs.job_id})
        self.assertIsNone(cnc.port)

    def test_start_checks_confirmation_modal_and_job_identity(self):
        cnc = Controller()
        cnc.port = StreamPort()
        cnc.jobs.load(parse_program("sample.nc", PROGRAM))
        status = lambda: cnc._accept_status("<Idle|WPos:0,0,0>")
        with patch.object(cnc, "_status", side_effect=status), patch.object(
            cnc, "_line", return_value=["[GC:G0 G54 M5]"]
        ):
            with self.assertRaises(ValueError):
                cnc.action("job_start", {"job_id": cnc.jobs.job_id})
            with self.assertRaises(ValueError):
                cnc.action("job_start", {"job_id": "old", "confirmed": True})
            result = cnc.action("job_start", {
                "job_id": cnc.jobs.job_id, "confirmed": True,
            })
            self.assertIn("lease", result)
        self.assertEqual(cnc.port.writes, [])
        self.assertNotIn("lease", cnc.jobs.status())

    def test_clear_never_opens_usb_and_rejects_active_job(self):
        cnc = Controller()
        cnc.action("job_load", {"name": "sample.nc", "content": PROGRAM})
        cnc.action("job_clear", {})
        self.assertEqual(cnc.jobs.state, "empty")
        self.assertIsNone(cnc.jobs.program)
        self.assertIsNone(cnc.port)
        cnc.jobs.load(parse_program("sample.nc", PROGRAM))
        cnc.jobs.start(cnc.jobs.job_id)
        with self.assertRaises(ValueError):
            cnc.action("job_clear", {})

    def test_start_rejects_spindle_on_and_unknown_work_position(self):
        for report, modal in (
            ("<Idle|WPos:0,0,0>", "[GC:G0 G54 M3]"),
            ("<Idle|MPos:0,0,0>", "[GC:G0 G54 M5]"),
            ("<Run|WPos:0,0,0>", "[GC:G0 G54 M5]"),
        ):
            cnc = Controller()
            cnc.port = StreamPort()
            cnc.jobs.load(parse_program("sample.nc", PROGRAM))
            status = lambda: cnc._accept_status(report)
            with patch.object(cnc, "_status", side_effect=status), patch.object(
                cnc, "_line", return_value=[modal]
            ):
                with self.assertRaises(ValueError):
                    cnc.action("job_start", {
                        "job_id": cnc.jobs.job_id, "confirmed": True,
                    })
            self.assertEqual(cnc.jobs.state, "ready")


class SenderTests(unittest.TestCase):
    """Check serial ownership, fragmented replies, hold and terminal states."""

    def setUp(self):
        self.cnc = Controller()
        self.port = StreamPort()
        self.cnc.port = self.port
        self.cnc._accept_status("<Idle|WPos:0,0,0>")
        self.jobs = self.cnc.jobs
        self.jobs.load(parse_program("sample.nc", PROGRAM))
        self.lease = self.jobs.start(self.jobs.job_id)["lease"]

    def test_one_inflight_ack_and_physical_completion(self):
        self.jobs.tick(self.cnc)
        self.assertEqual(self.port.writes[-1], b"G21G90G94G54\n")
        self.jobs.tick(self.cnc)
        commands = sum(data.endswith(b"\n") for data in self.port.writes)
        self.assertEqual(commands, 1)
        self.port.receive = b"<Run|WPos:0,0,0>\nok"
        self.jobs.tick(self.cnc)
        self.assertEqual(self.jobs.acknowledged, 0)
        self.port.receive = b"\n"
        self.jobs.tick(self.cnc)
        self.assertEqual(self.jobs.acknowledged, 1)
        for _ in self.jobs.program["lines"][1:]:
            self.port.receive = b"ok\n"
            self.jobs.tick(self.cnc)
        self.assertEqual(self.jobs.state, "draining")
        self.port.receive = b"<Run|WPos:1,0,3>\n"
        self.jobs.tick(self.cnc)
        self.assertEqual(self.jobs.state, "draining")
        self.port.receive = b"<Idle|WPos:1,0,3>\n"
        self.jobs.tick(self.cnc)
        self.assertEqual(self.jobs.state, "completed")
        self.assertFalse(self.port.closed)

    def test_pause_and_explicit_resume_do_not_send_more_lines(self):
        self.jobs.tick(self.cnc)
        self.jobs.control("pause")
        self.jobs.tick(self.cnc)
        self.assertIn(b"!", self.port.writes)
        self.port.receive = b"ok\n<Hold:0|WPos:0,0,0>\n"
        self.jobs.tick(self.cnc)
        self.assertEqual(self.jobs.state, "paused")
        commands = sum(data.endswith(b"\n") for data in self.port.writes)
        self.assertEqual(commands, 1)
        self.jobs.control("resume", self.jobs.job_id)
        self.jobs.tick(self.cnc)
        self.assertIn(b"~", self.port.writes)
        self.assertEqual(self.jobs.state, "resuming")
        self.port.receive = b"<Run|WPos:0,0,0>\n"
        self.jobs.tick(self.cnc)
        self.assertEqual(self.jobs.state, "running")
        commands = sum(data.endswith(b"\n") for data in self.port.writes)
        self.assertEqual(commands, 2)

    def test_expired_owner_holds_without_auto_resume(self):
        future = time.monotonic() + 9
        with patch("monitor.jobs.time.monotonic", return_value=future):
            self.cnc.report_time = time.monotonic() + 9
            self.jobs.tick(self.cnc)
        self.assertEqual(self.jobs.state, "pausing")
        self.assertIn(b"!", self.port.writes)
        self.assertNotIn(b"~", self.port.writes)
        with self.assertRaises(ValueError):
            self.jobs.heartbeat("wrong-viewer")

    def test_stop_resets_closes_and_cannot_resume(self):
        self.jobs.control("stop")
        self.jobs.tick(self.cnc)
        self.assertIn(b"!\x18", self.port.writes)
        self.assertTrue(self.port.closed)
        self.assertEqual(self.jobs.state, "stopped")
        with self.assertRaises(ValueError):
            self.jobs.control("resume", self.jobs.job_id)

    def test_alarm_reset_and_error_abort_without_retry(self):
        for reply in (b"error:20\n", b"ALARM:1\n", b"Grbl 1.1h\n"):
            with self.subTest(reply=reply):
                self.setUp()
                self.jobs.tick(self.cnc)
                self.port.receive = reply
                self.jobs.tick(self.cnc)
                self.assertEqual(self.jobs.state, "failed")
                self.assertTrue(self.port.closed)
                commands = sum(
                    data.endswith(b"\n") for data in self.port.writes
                )
                self.assertEqual(commands, 1)

    def test_active_job_rejects_manual_commands_and_upload(self):
        for action in ("jog", "zero_xy", "spindle_on", "disconnect", "connect"):
            with self.assertRaises(ValueError):
                self.cnc.action(action, {})
        with self.assertRaises(ValueError):
            self.cnc.action("job_load", {"name": "new.nc", "content": PROGRAM})
        self.assertEqual(self.port.writes, [])

    def test_stale_status_and_ack_timeout_fail_without_retry(self):
        self.jobs.tick(self.cnc)
        now = time.monotonic()
        with patch("monitor.jobs.time.monotonic", return_value=now + 121):
            self.jobs.heartbeat_at = now + 121
            self.cnc.report_time = now + 121
            self.jobs.tick(self.cnc)
        self.assertEqual(self.jobs.state, "failed")
        self.setUp()
        self.cnc.report_time = time.monotonic() - 4
        self.jobs.tick(self.cnc)
        self.assertEqual(self.jobs.state, "failed")


if __name__ == "__main__":
    unittest.main()

# ---------------------------------------------------------------------------
# end of file
# ---------------------------------------------------------------------------
