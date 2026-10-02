# ---------------------------------------------------------------------------
# test_cnc.py
# 2026-10-02
# - Hardware-free command validation, status and failure behavior tests.
# ---------------------------------------------------------------------------
"""Test manual CNC integration without opening USB or moving a machine."""

import unittest

from monitor.cnc import Controller, manual_command, parse_status


class FakePort:
    """Minimal serial fixture with prerecorded controller replies."""

    def __init__(self, replies):
        self.replies = list(replies)
        self.writes = []
        self.closed = False

    def write(self, data):
        self.writes.append(data)

    def readline(self, size):
        if self.replies:
            return self.replies.pop(0).encode() + b"\n"
        return b""

    def close(self):
        self.closed = True


class CncTests(unittest.TestCase):
    """Verify bounded commands and conservative device failure handling."""

    def test_commands(self):
        self.assertEqual(
            manual_command("jog", {"axis": "Z", "distance": -0.1,
                                   "feed": 100}),
            "$J=G91 G21 Z-0.1 F100",
        )
        self.assertEqual(manual_command("zero_z", {}), "G10 L20 P1 Z0")
        self.assertEqual(manual_command("spindle_off", {}), "M5")
        self.assertEqual(
            manual_command("spindle_on", {"power": 300}), "M3 S300",
        )

    def test_invalid_commands(self):
        for action in ("home", "reset", "unlock", "start", "G0 X50"):
            with self.assertRaises(ValueError):
                manual_command(action, {})
        for distance in (0, 11, float("nan"), float("inf")):
            with self.assertRaises(ValueError):
                manual_command("jog", {
                    "axis": "X", "distance": distance, "feed": 100,
                })
        with self.assertRaises(ValueError):
            manual_command("jog", {
                "axis": "X\nM3", "distance": 1, "feed": 100,
            })

    def test_work_position_and_cached_offset(self):
        cnc = Controller()
        cnc.port = FakePort([
            "<Idle|MPos:10,20,30|WCO:1,2,3>",
            "<Idle|MPos:11,22,33>",
        ])
        cnc._status()
        self.assertEqual(cnc.status()["position"], [9, 18, 27])
        cnc._status()
        self.assertEqual(cnc.status()["position"], [10, 20, 30])

    def test_unknown_position_is_not_zero(self):
        cnc = Controller()
        cnc.port = FakePort(["<Idle|MPos:10,20,30>"])
        cnc._status()
        self.assertIsNone(cnc.status()["position"])
        with self.assertRaises(ValueError):
            parse_status("<Idle|WPos:nan,1,2>")

    def test_busy_machine_rejects_motion(self):
        cnc = Controller()
        cnc.port = FakePort(["<Run|WPos:1,2,3>"])
        with self.assertRaises(ValueError):
            cnc.action("jog", {"axis": "X", "distance": 1, "feed": 100})
        self.assertEqual(cnc.port.writes, [b"?"])

    def test_acknowledged_manual_command(self):
        cnc = Controller()
        cnc.port = FakePort([
            "<Idle|WPos:0,0,0>", "[GC:G0 G54 G17 G21]", "ok",
            "ok", "<Jog|WPos:0.1,0,0>",
        ])
        cnc.action("jog", {"axis": "X", "distance": 0.1, "feed": 100})
        self.assertIn(b"$J=G91 G21 X0.1 F100\n", cnc.port.writes)
        self.assertEqual(cnc.status()["state"], "Jog")

    def test_reset_closes_without_retry(self):
        cnc = Controller()
        port = FakePort(["Grbl 1.1h"])
        cnc.port = port
        with self.assertRaises(RuntimeError):
            cnc.action("spindle_off", {})
        self.assertTrue(port.closed)
        self.assertIsNone(cnc.port)
        self.assertEqual(port.writes, [b"?"])

    def test_jog_cancel_does_not_require_idle(self):
        cnc = Controller()
        cnc.port = FakePort(["<Jog|WPos:1,2,3>"])
        cnc.action("jog_cancel", {})
        self.assertEqual(cnc.port.writes, [b"\x85", b"?"])


if __name__ == "__main__":
    unittest.main()

# ---------------------------------------------------------------------------
# end of file
# ---------------------------------------------------------------------------
