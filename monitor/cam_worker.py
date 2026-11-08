# ---------------------------------------------------------------------------
# cam_worker.py
# 2026-11-08
# - Bounded offline CAM subprocess; writes artifacts but has no machine API.
# ---------------------------------------------------------------------------
"""Invoked by the collection runner in a private-device systemd sandbox."""

import json
import hashlib
from importlib.metadata import version
import os
from pathlib import Path
import resource
import sys
import time


def main():
    """Generate a result or a persisted, readable failure; never load a job."""
    os.nice(10)
    resource.setrlimit(resource.RLIMIT_CPU, (150, 150))
    resource.setrlimit(resource.RLIMIT_FSIZE, (16 * 1024 * 1024,) * 2)
    resource.setrlimit(resource.RLIMIT_NOFILE, (128, 128))
    directory = Path(sys.argv[1]).resolve()
    started = time.monotonic()
    try:
        if version("gerbonara") != "1.6.3" or version("shapely") != "2.2.0":
            raise ValueError("Niezgodna wersja zależności CAM.")
        from monitor.cam_geometry import generate
        request = json.loads((directory / "request.json").read_text())
        source = (directory / "source.zip").read_bytes()
        if hashlib.sha256(source).hexdigest() != request["sourceSha256"]:
            raise ValueError("Źródłowy pakiet CAM został zmieniony.")
        for name, expected in request["implementationHashes"].items():
            filename = Path(__file__).parent / name
            if hashlib.sha256(filename.read_bytes()).hexdigest() != expected:
                raise ValueError("Silnik CAM zmienił się; oblicz ponownie.")
        report, preview, content = generate(
            source, request["project"],
            request["profile"], request["clearanceMm"], directory)
        (directory / "preview.json").write_text(json.dumps(preview))
        if content is not None:
            (directory / "isolation.nc").write_text(content, encoding="ascii")
        result = {"state": "ready" if content is not None else "blocked",
                  "report": report}
    except Exception as error:
        result = {"state": "failed", "error": str(error)[:500]}
    result["durationSeconds"] = round(time.monotonic() - started, 2)
    temporary = directory / "result.tmp"
    temporary.write_text(json.dumps(result, ensure_ascii=False))
    temporary.replace(directory / "result.json")


if __name__ == "__main__":
    main()

# ---------------------------------------------------------------------------
# end of file
# ---------------------------------------------------------------------------
