# ---------------------------------------------------------------------------
# test_probes.py
# 2026-10-18
# - Hardware-free probe diagnostics, guarded motion and failure handling.
# ---------------------------------------------------------------------------
"""Simulated serial input only; no controller or machine is opened."""

import time
import unittest
from unittest.mock import patch

from monitor.cnc import Controller, parse_status


class Port:
    """Separate input bytes and output commands for asynchronous assertions."""

    def __init__(self):
        self.receive = b""
        self.writes = []
        self.closed = False

    @property
    def in_waiting(self):
        return len(self.receive)

    def read(self, count):
        result = self.receive[:count]
        self.receive = self.receive[count:]
        return result

    def write(self, value):
        self.writes.append(value)

    def close(self):
        self.closed = True


class ProbeTests(unittest.TestCase):
    """Exercise success and every uncertain path without physical motion."""

    def setUp(self):
        self.cnc = Controller()
        self.port = Port()
        self.cnc.port = self.port
        self.cnc.info = ["$6=0", "$13=0"]
        self.cnc._accept_status("<Idle|MPos:0,0,6|WCO:0,0,5|Pn:P>")
        self.cnc._accept_status("<Idle|MPos:0,0,6|WCO:0,0,5>")
        self.payload = {"confirmed": True, "distance": 1, "feed": 20,
                        "position": [0, 0, 1]}
        self.modal = ["[GC:G0 G54 G17 G21 G90 G94 M5 M9 T0 F100 S0]"]

    def start(self):
        """Only the worker should send G38 after successful preflight."""
        with patch.object(self.cnc, "_status"), patch.object(
            self.cnc, "_line", return_value=self.modal
        ):
            return self.cnc.action("probe_start", self.payload)

    def receive(self, text):
        self.port.receive += text.encode("ascii")
        self.cnc.probe.tick(self.cnc)

    def test_pin_state_is_current_not_latched(self):
        self.assertTrue(parse_status("<Idle|WPos:0,0,0|Pn:ZP>")[
            "probe_triggered"
        ])
        self.assertFalse(parse_status("<Idle|WPos:0,0,0|Pn:Z>")[
            "probe_triggered"
        ])
        self.assertFalse(self.cnc.status()["probe_triggered"])
        self.assertTrue(self.cnc.status()["probe_tested"])
        self.cnc.report_time = time.monotonic() - 3
        self.assertIsNone(self.cnc.status()["probe_triggered"])
        self.cnc._close("test")
        self.assertFalse(self.cnc.status()["probe_tested"])
        self.assertIsNone(self.cnc.status()["probe_triggered"])

    def test_confirmation_bounds_and_actual_pin_test_required(self):
        for key, value in (
            ("confirmed", False), ("distance", 0), ("distance", 6),
            ("distance", float("nan")), ("feed", 9), ("feed", 61),
            ("position", [0, 0, 2]),
        ):
            with self.subTest(key=key, value=value):
                old = self.payload[key]
                self.payload[key] = value
                with self.assertRaises(ValueError):
                    self.start()
                self.payload[key] = old
        self.cnc.probe_tested = False
        with self.assertRaises(ValueError):
            self.start()
        self.cnc.probe_tested = True
        self.cnc._accept_status("<Idle|MPos:0,0,6|Pn:P>")
        with self.assertRaises(ValueError):
            self.start()
        self.assertEqual(self.port.writes, [])

    def test_modal_units_inversion_and_busy_guards(self):
        for modal in (
            "[GC:G0 G54 G17 G21 G90 G94 M3]",
            "[GC:G0 G55 G17 G21 G90 G94 M5]",
            "[GC:G0 G54 G17 G20 G90 G94 M5]",
            "[GC:G0 G54 G17 G21 G91 G94 M5]",
        ):
            self.modal = [modal]
            with self.assertRaises(ValueError):
                self.start()
        for settings in (["$6=1", "$13=0"], ["$6=0", "$13=1"], []):
            self.cnc.info = settings
            with self.assertRaises(ValueError):
                self.start()
        self.assertEqual(self.port.writes, [])

    def test_success_uses_contact_not_stopped_position(self):
        result = self.start()
        self.assertIn("probe_lease", result)
        self.assertEqual(self.port.writes, [])
        self.cnc.probe.tick(self.cnc)
        self.assertIn(b"G90G38.2Z0.0000F20\n", self.port.writes)
        self.receive("[PRB:0,0,5.4:1]\nok\n")
        self.assertEqual(self.cnc.probe.state, "contact_wait")
        self.assertFalse(any(b"G10" in value for value in self.port.writes))
        self.receive("<Idle|MPos:0,0,5.397|Pn:P>\n")
        self.assertIn(b"G10L20P1Z-0.0030\n", self.port.writes)
        self.receive("ok\n")
        self.assertIn(b"G0Z1\n", self.port.writes)
        self.receive("ok\n<Run|MPos:0,0,5.6|WCO:0,0,5.4>\n")
        self.assertTrue(self.cnc.probe.active())
        self.receive("<Idle|MPos:0,0,6.4|WCO:0,0,5.4>\n")
        self.assertEqual(self.cnc.probe.state, "completed")
        self.assertAlmostEqual(self.cnc.status()["position"][2], 1)
        self.assertFalse(self.port.closed)

    def test_failures_do_not_zero_or_retry(self):
        for reply in (
            "ALARM:5\n", "error:20\n", "Grbl 1.1h\n", "ok\n",
            "[PRB:0,0,5.4:0]\n", "[PRB:nan,0,5:1]\n",
            "[PRB:1,0,5.4:1]\n", "[PRB:0,0,4:1]\n",
            "<Hold:0|MPos:0,0,6>\n",
        ):
            with self.subTest(reply=reply):
                self.setUp()
                self.start()
                self.receive(reply)
                self.assertEqual(self.cnc.probe.state, "failed")
                self.assertTrue(self.port.closed)
                self.assertIn(b"!\x18", self.port.writes)
                self.assertFalse(any(b"G10" in v for v in self.port.writes))

    def test_stop_and_browser_loss_abort(self):
        self.start()
        for action in ("jog", "zero_z", "connect", "job_clear", "job_stop"):
            with self.assertRaises(ValueError):
                self.cnc.action(action, {})
        self.cnc.action("probe_stop", {})
        self.cnc.probe.tick(self.cnc)
        self.assertEqual(self.cnc.probe.state, "stopped")
        self.assertNotIn(b"G90G38.2Z0.0000F20\n", self.port.writes)
        self.setUp()
        lease = self.start()["probe_lease"]
        with self.assertRaises(ValueError):
            self.cnc.action("probe_heartbeat", {"lease": "observer"})
        self.cnc.action("probe_heartbeat", {"lease": lease})
        self.cnc.probe.heartbeat_at -= 9
        self.cnc.probe.tick(self.cnc)
        self.assertEqual(self.cnc.probe.state, "failed")
        self.assertTrue(self.port.closed)

    def test_timeout_and_no_status_abort(self):
        self.start()
        self.cnc.probe.deadline = time.monotonic() - 1
        self.cnc.probe.tick(self.cnc)
        self.assertTrue(self.port.closed)

    def test_busy_job_and_machine_cannot_start(self):
        self.cnc.jobs.state = "running"
        with self.assertRaises(ValueError):
            self.start()
        self.cnc.jobs.state = "empty"
        self.cnc._accept_status("<Run|MPos:0,0,6>")
        with self.assertRaises(ValueError):
            self.start()
        self.assertEqual(self.port.writes, [])

    def test_stopped_coordinates_and_stuck_contact_are_checked(self):
        self.start()
        self.receive("[PRB:0,0,5.4:1]\nok\n")
        self.receive("<Idle|MPos:1,0,5.397|Pn:P>\n")
        self.assertEqual(self.cnc.probe.state, "failed")
        self.assertFalse(any(b"G10" in v for v in self.port.writes))
        self.setUp()
        self.start()
        self.receive("[PRB:0,0,5.4:1]\nok\n")
        self.receive("<Idle|MPos:0,0,5.397|Pn:P>\n")
        self.receive("ok\nok\n")
        self.receive("<Idle|MPos:0,0,6.4|WCO:0,0,5.4|Pn:P>\n")
        self.assertEqual(self.cnc.probe.state, "failed")
        self.assertTrue(self.port.closed)
        self.setUp()
        self.start()
        self.cnc.report_time -= 4
        self.cnc.probe.tick(self.cnc)
        self.assertTrue(self.port.closed)


if __name__ == "__main__":
    unittest.main()

# ---------------------------------------------------------------------------
# end of file
# ---------------------------------------------------------------------------
