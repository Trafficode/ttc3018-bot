# ---------------------------------------------------------------------------
# server.py
# 2026-10-02
# - Loopback-only dashboard, shared MJPEG camera and cached DHT22 telemetry.
# ---------------------------------------------------------------------------
"""Serve monitoring over Tailscale Serve; never access CNC serial ports."""

import argparse
import json
import logging
import os
from pathlib import Path
import signal
import selectors
import subprocess
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent.parent
MAX_FRAME_BYTES = 2 * 1024 * 1024


def utc_now():
    """Return an unambiguous timestamp for successful measurements."""
    return datetime.now(timezone.utc).isoformat()


class JpegFrames:
    """Split fragmented MJPEG output with a bounded incomplete-frame buffer."""

    def __init__(self):
        self.buffer = bytearray()

    def feed(self, chunk):
        """Return complete JPEG frames found in a pipe chunk."""
        self.buffer.extend(chunk)
        frames = []
        while True:
            start = self.buffer.find(b"\xff\xd8")
            if start < 0:
                self.buffer = self.buffer[-1:]
                break
            if start:
                del self.buffer[:start]
            end = self.buffer.find(b"\xff\xd9", 2)
            if end < 0:
                if len(self.buffer) > MAX_FRAME_BYTES:
                    self.buffer = self.buffer[-1:]
                break
            end += 2
            if end <= MAX_FRAME_BYTES:
                frames.append(bytes(self.buffer[:end]))
            del self.buffer[:end]
        return frames


class State:
    """Share one latest frame and sensor reading among all viewers."""

    def __init__(self):
        self.condition = threading.Condition()
        self.frame = None
        self.frame_number = 0
        self.frame_time = None
        self.camera_error = "Camera starting"
        self.sensor_time = None
        self.sensor_timestamp = None
        self.temperature = None
        self.humidity = None
        self.sensor_error = "Sensor starting"

    def camera_frame(self, frame):
        """Publish a fresh frame and wake waiting stream clients."""
        with self.condition:
            self.frame = frame
            self.frame_number += 1
            self.frame_time = time.monotonic()
            self.camera_error = None
            self.condition.notify_all()

    def sensor_reading(self, temperature, humidity):
        """Publish a successful reading without inventing a freshness time."""
        with self.condition:
            self.temperature = temperature
            self.humidity = humidity
            self.sensor_time = time.monotonic()
            self.sensor_timestamp = utc_now()
            self.sensor_error = None

    def error(self, device, message):
        """Preserve the last success, but expose the latest device error."""
        with self.condition:
            if device == "camera":
                self.camera_error = message
            else:
                self.sensor_error = message

    def status(self):
        """Report ages and health; no machine state is implied."""
        with self.condition:
            now = time.monotonic()
            camera_age = None
            sensor_age = None
            if self.frame_time is not None:
                camera_age = round(now - self.frame_time, 1)
            if self.sensor_time is not None:
                sensor_age = round(now - self.sensor_time, 1)
            camera_ok = (
                camera_age is not None and camera_age < 5
                and self.camera_error is None
            )
            sensor_ok = (
                sensor_age is not None and sensor_age < 20
                and self.sensor_error is None
            )
            return {
                "schema_version": 1,
                "camera": {
                    "ok": camera_ok,
                    "age_seconds": camera_age,
                    "frame_number": self.frame_number,
                    "error": self.camera_error,
                },
                "environment": {
                    "ok": sensor_ok,
                    "temperature_c": self.temperature,
                    "humidity_percent": self.humidity,
                    "timestamp": self.sensor_timestamp,
                    "age_seconds": sensor_age,
                    "error": self.sensor_error,
                },
                "cnc": {"connected": False, "reason": "Not implemented"},
            }


def camera_worker(state, stop, options):
    """Own one camera subprocess; restart only that process on capture errors."""
    command = [
        "rpicam-vid", "--nopreview", "--timeout", "0",
        "--codec", "mjpeg", "--flush", "--output", "-",
        "--camera", str(options.camera),
        "--width", "960", "--height", "540",
        "--framerate", "8", "--quality", "65",
    ]
    while not stop.is_set():
        process = None
        try:
            process = subprocess.Popen(
                command, stdout=subprocess.PIPE, bufsize=0,
            )
            parser = JpegFrames()
            with selectors.DefaultSelector() as selector:
                selector.register(process.stdout, selectors.EVENT_READ)
                while not stop.is_set():
                    if not selector.select(timeout=1):
                        continue
                    chunk = process.stdout.read(65536)
                    if not chunk:
                        raise RuntimeError("Camera capture process ended")
                    for frame in parser.feed(chunk):
                        state.camera_frame(frame)
        except (OSError, RuntimeError) as error:
            state.error("camera", str(error))
            logging.warning("Camera: %s", error)
        finally:
            if process is not None:
                process.terminate()
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
                process.stdout.close()
        stop.wait(5)


def sensor_worker(state, stop, options):
    """Own the DHT22 reader; sample at most once every five seconds."""
    sensor = None
    try:
        import adafruit_dht
        import board

        pin = getattr(board, f"D{options.gpio}")
        sensor = adafruit_dht.DHT22(pin, use_pulseio=False)
        while not stop.is_set():
            try:
                temperature = sensor.temperature
                humidity = sensor.humidity
                if temperature is None or humidity is None:
                    raise RuntimeError("No sensor reading")
                if not -40 <= temperature <= 80 or not 0 <= humidity <= 100:
                    raise RuntimeError("Sensor reading outside range")
                state.sensor_reading(temperature, humidity)
            except RuntimeError as error:
                state.error("sensor", str(error))
            stop.wait(5)
    except Exception as error:
        # Keep the dashboard available even if GPIO setup or a driver fails.
        state.error("sensor", str(error))
        logging.exception("Sensor worker stopped")
    finally:
        if sensor is not None:
            sensor.exit()


class MonitorServer(ThreadingHTTPServer):
    """Loopback HTTP server with shared workers and at most four streams."""

    daemon_threads = True

    def __init__(self, port, state, stop):
        super().__init__(("127.0.0.1", port), Handler)
        self.state = state
        self.stop = stop
        self.stream_slots = threading.BoundedSemaphore(4)


class Handler(BaseHTTPRequestHandler):
    """Read-only fixed routes; no filesystem browsing or control commands."""

    def setup(self):
        super().setup()
        self.connection.settimeout(10)

    def respond(self, status, content_type, body):
        """Write an uncached response with conservative browser headers."""
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Cross-Origin-Resource-Policy", "same-origin")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; frame-ancestors 'none'; "
            "base-uri 'none'; form-action 'none'",
        )
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        """Serve the dashboard, status, fresh snapshot or shared MJPEG stream."""
        path = urlsplit(self.path).path
        assets = {
            "/": ("index.html", "text/html; charset=utf-8"),
            "/style.css": ("style.css", "text/css; charset=utf-8"),
            "/app.js": ("app.js", "text/javascript; charset=utf-8"),
        }
        try:
            if path in assets:
                filename, content_type = assets[path]
                self.respond(
                    200, content_type, (ROOT / "web" / filename).read_bytes(),
                )
            elif path == "/api/status":
                body = json.dumps(self.server.state.status()).encode()
                self.respond(200, "application/json", body)
            elif path == "/camera.jpg":
                with self.server.state.condition:
                    fresh = self.server.state.status()["camera"]["ok"]
                    frame = self.server.state.frame
                if not fresh:
                    self.respond(503, "text/plain", b"Camera unavailable")
                else:
                    self.respond(200, "image/jpeg", frame)
            elif path == "/camera.mjpg":
                self.stream()
            else:
                self.respond(404, "text/plain", b"Not found")
        except (BrokenPipeError, ConnectionResetError, TimeoutError):
            pass

    def stream(self):
        """Broadcast latest frames; do not queue video for a slow viewer."""
        if not self.server.stream_slots.acquire(blocking=False):
            self.respond(503, "text/plain", b"Too many viewers")
            return
        try:
            if not self.server.state.status()["camera"]["ok"]:
                self.respond(503, "text/plain", b"Camera unavailable")
                return
            self.send_response(200)
            self.send_header(
                "Content-Type", "multipart/x-mixed-replace; boundary=frame",
            )
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Cross-Origin-Resource-Policy", "same-origin")
            self.end_headers()
            previous = -1
            while not self.server.stop.is_set():
                with self.server.state.condition:
                    self.server.state.condition.wait_for(
                        lambda: self.server.state.frame_number != previous
                        or self.server.stop.is_set(), timeout=5,
                    )
                    if not self.server.state.status()["camera"]["ok"]:
                        return
                    previous = self.server.state.frame_number
                    frame = self.server.state.frame
                header = (
                    b"--frame\r\nContent-Type: image/jpeg\r\n"
                    + f"Content-Length: {len(frame)}\r\n\r\n".encode()
                )
                self.wfile.write(header + frame + b"\r\n")
                self.wfile.flush()
        finally:
            self.server.stream_slots.release()

    def log_message(self, format_string, *arguments):
        """Avoid logging every telemetry poll; systemd captures errors."""
        return


def main():
    """Run the fixed loopback service; systemd owns the process lifecycle."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8766)
    parser.add_argument(
        "--gpio", type=int, default=int(os.getenv("DHT_GPIO", "17")),
    )
    parser.add_argument(
        "--camera", type=int, default=int(os.getenv("CAMERA_INDEX", "0")),
    )
    options = parser.parse_args()
    if not 1024 <= options.port <= 65535:
        parser.error("--port must be between 1024 and 65535")
    if not 0 <= options.gpio <= 27 or not 0 <= options.camera <= 3:
        parser.error("Invalid BCM GPIO number or camera index")
    logging.basicConfig(level=logging.INFO)
    stop = threading.Event()
    state = State()
    server = MonitorServer(options.port, state, stop)

    def request_stop(signum, frame):
        stop.set()

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)
    workers = []
    for worker in (camera_worker, sensor_worker):
        thread = threading.Thread(
            target=worker, args=(state, stop, options), daemon=True,
        )
        workers.append(thread)
        thread.start()
    server.timeout = 0.5
    logging.info("Monitoring on 127.0.0.1:%s; no CNC access", options.port)
    try:
        while not stop.is_set():
            server.handle_request()
    finally:
        stop.set()
        with state.condition:
            state.condition.notify_all()
        server.server_close()
        for thread in workers:
            thread.join(timeout=4)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

# ---------------------------------------------------------------------------
# end of file
# ---------------------------------------------------------------------------
