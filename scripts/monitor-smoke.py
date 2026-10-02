# ---------------------------------------------------------------------------
# monitor-smoke.py
# 2026-10-02
# - Bounded monitoring acceptance test with control tokens omitted from output.
# ---------------------------------------------------------------------------
"""Check the running service; no direct GPIO, camera or CNC access."""

import json
from pathlib import Path
import sys
import time
from urllib.request import urlopen

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from monitor.server import JpegFrames


def main():
    """Require fresh sensor data, a snapshot and multiple video frames."""
    base = "http://127.0.0.1:8766"
    deadline = time.monotonic() + 20
    while True:
        with urlopen(base + "/api/status", timeout=3) as response:
            status = json.load(response)
        status.pop("control_token", None)
        if status["camera"]["ok"] and status["environment"]["ok"]:
            break
        if time.monotonic() >= deadline:
            raise RuntimeError(f"Monitoring not healthy: {status}")
        time.sleep(1)
    with urlopen(base + "/camera.jpg", timeout=3) as response:
        snapshot = response.read(2 * 1024 * 1024)
        if not snapshot.startswith(b"\xff\xd8"):
            raise RuntimeError("Snapshot is not a JPEG")
    parser = JpegFrames()
    frame_count = 0
    deadline = time.monotonic() + 8
    with urlopen(base + "/camera.mjpg", timeout=3) as response:
        while frame_count < 2 and time.monotonic() < deadline:
            chunk = response.read(32768)
            if not chunk:
                break
            frame_count += len(parser.feed(chunk))
    if frame_count < 2:
        raise RuntimeError("Video did not deliver multiple frames")
    print(json.dumps({
        "status": "ok", "video_frames": frame_count,
        "snapshot_bytes": len(snapshot), "telemetry": status,
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

# ---------------------------------------------------------------------------
# end of file
# ---------------------------------------------------------------------------
