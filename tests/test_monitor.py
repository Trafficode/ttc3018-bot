# ---------------------------------------------------------------------------
# test_monitor.py
# 2026-10-02
# - Hardware-free tests for stream parsing, freshness and read-only HTTP routes.
# ---------------------------------------------------------------------------
"""Validate monitoring without camera, GPIO, USB or Tailscale access."""

import json
import threading
import time
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from monitor.server import JpegFrames, MAX_FRAME_BYTES, MonitorServer, State


class FrameTests(unittest.TestCase):
    """Cover JPEG splitting and bounded buffering."""

    def test_fragmented_and_multiple_frames(self):
        parser = JpegFrames()
        self.assertEqual(parser.feed(b"noise\xff"), [])
        self.assertEqual(parser.feed(b"\xd8abc\xff"), [])
        self.assertEqual(
            parser.feed(b"\xd9\xff\xd8xyz\xff\xd9"),
            [b"\xff\xd8abc\xff\xd9", b"\xff\xd8xyz\xff\xd9"],
        )

    def test_oversized_partial_frame_is_discarded(self):
        parser = JpegFrames()
        parser.feed(b"\xff\xd8" + b"x" * MAX_FRAME_BYTES)
        self.assertLessEqual(len(parser.buffer), 1)
        frame = b"\xff\xd8ok\xff\xd9"
        self.assertEqual(parser.feed(frame), [frame])


class StatusTests(unittest.TestCase):
    """Cover missing data, freshness and visible failures."""

    def test_initial_state_is_not_healthy(self):
        status = State().status()
        self.assertFalse(status["camera"]["ok"])
        self.assertFalse(status["environment"]["ok"])
        self.assertFalse(status["cnc"]["connected"])

    def test_stale_sensor_and_error_keep_original_timestamp(self):
        state = State()
        state.sensor_reading(24.0, 60.0)
        timestamp = state.sensor_timestamp
        state.sensor_time = time.monotonic() - 30
        state.error("sensor", "Checksum error")
        status = state.status()["environment"]
        self.assertFalse(status["ok"])
        self.assertEqual(status["timestamp"], timestamp)
        self.assertEqual(status["error"], "Checksum error")

    def test_camera_freshness_and_recovery(self):
        state = State()
        state.camera_frame(b"frame")
        self.assertTrue(state.status()["camera"]["ok"])
        state.error("camera", "Capture ended")
        self.assertFalse(state.status()["camera"]["ok"])
        state.camera_frame(b"next")
        self.assertTrue(state.status()["camera"]["ok"])
        state.frame_time = time.monotonic() - 6
        self.assertFalse(state.status()["camera"]["ok"])


class HttpTests(unittest.TestCase):
    """Exercise a loopback server without starting hardware workers."""

    def setUp(self):
        self.state = State()
        self.stop = threading.Event()
        self.server = MonitorServer(0, self.state, self.stop)
        self.thread = threading.Thread(target=self.server.serve_forever)
        self.thread.start()
        port = self.server.server_address[1]
        self.url = f"http://127.0.0.1:{port}"

    def tearDown(self):
        self.stop.set()
        with self.state.condition:
            self.state.condition.notify_all()
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    def test_dashboard_and_status(self):
        self.assertEqual(self.server.server_address[0], "127.0.0.1")
        with urlopen(self.url + "/", timeout=2) as response:
            self.assertIn(b"TTC3018", response.read())
            self.assertEqual(response.headers["Cache-Control"], "no-store")
        with urlopen(self.url + "/api/status", timeout=2) as response:
            status = json.load(response)
            self.assertEqual(status["schema_version"], 1)
            self.assertFalse(status["cnc"]["connected"])

    def test_unknown_files_and_post_are_rejected(self):
        with self.assertRaises(HTTPError) as error:
            urlopen(self.url + "/../.env", timeout=2)
        self.assertEqual(error.exception.code, 404)
        request = Request(self.url + "/api/status", data=b"start")
        with self.assertRaises(HTTPError) as error:
            urlopen(request, timeout=2)
        self.assertEqual(error.exception.code, 501)

    def test_control_requires_token_and_rejects_unknown_actions(self):
        request = Request(
            self.url + "/api/cnc/action", data=b'{"action":"home"}',
            headers={"Content-Type": "application/json"},
        )
        with self.assertRaises(HTTPError) as error:
            urlopen(request, timeout=2)
        self.assertEqual(error.exception.code, 403)
        request.add_header("X-PiloMill-Token", self.server.control_token)
        with self.assertRaises(HTTPError) as error:
            urlopen(request, timeout=2)
        self.assertEqual(error.exception.code, 400)
        self.assertIsNone(self.server.cnc.port)

    def test_snapshot_is_unavailable_until_fresh(self):
        with self.assertRaises(HTTPError) as error:
            urlopen(self.url + "/camera.jpg", timeout=2)
        self.assertEqual(error.exception.code, 503)
        frame = b"\xff\xd8ok\xff\xd9"
        self.state.camera_frame(frame)
        with urlopen(self.url + "/camera.jpg", timeout=2) as response:
            self.assertEqual(response.read(), frame)
        self.state.frame_time = time.monotonic() - 6
        with self.assertRaises(HTTPError) as error:
            urlopen(self.url + "/camera.jpg", timeout=2)
        self.assertEqual(error.exception.code, 503)

    def test_stream_viewer_limit(self):
        for index in range(4):
            self.assertTrue(self.server.stream_slots.acquire(blocking=False))
        try:
            with self.assertRaises(HTTPError) as error:
                urlopen(self.url + "/camera.mjpg", timeout=2)
            self.assertEqual(error.exception.code, 503)
        finally:
            for index in range(4):
                self.server.stream_slots.release()

    def test_stream_returns_frame_and_releases_slot(self):
        frame = b"\xff\xd8test\xff\xd9"
        self.state.camera_frame(frame)
        with urlopen(self.url + "/camera.mjpg", timeout=2) as response:
            self.assertIn("multipart", response.headers["Content-Type"])
            self.assertEqual(response.readline(), b"--frame\r\n")
            self.assertIn(b"image/jpeg", response.readline())
            response.readline()
            response.readline()
            self.assertEqual(response.read(len(frame)), frame)
        self.stop.set()
        with self.state.condition:
            self.state.condition.notify_all()
        deadline = time.monotonic() + 1
        while time.monotonic() < deadline:
            acquired = self.server.stream_slots.acquire(blocking=False)
            if acquired:
                self.server.stream_slots.release()
                break
            time.sleep(0.01)
        self.assertTrue(acquired)


if __name__ == "__main__":
    unittest.main()

# ---------------------------------------------------------------------------
# end of file
# ---------------------------------------------------------------------------
