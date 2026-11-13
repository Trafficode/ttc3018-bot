# ---------------------------------------------------------------------------
# cam_worker.py
# 2026-11-13
# - Compute only selected operations without a V-bit dependency for mechanics.
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
        from monitor.cam_geometry import generate, mechanical_preview
        from monitor.pcb_flow import selected_operations
        request = json.loads((directory / "request.json").read_text())
        source = (directory / "source.zip").read_bytes()
        if hashlib.sha256(source).hexdigest() != request["sourceSha256"]:
            raise ValueError("Źródłowy pakiet CAM został zmieniony.")
        for name, expected in request["implementationHashes"].items():
            filename = Path(__file__).parent / name
            if hashlib.sha256(filename.read_bytes()).hexdigest() != expected:
                raise ValueError("Silnik CAM zmienił się; oblicz ponownie.")
        requested = selected_operations(request["workflow"]) if (
            request.get("workflow")) else ["isolation"]
        if "isolation" in requested:
            report, preview, content = generate(
                source, request["project"], request["profile"],
                request["clearanceMm"], directory)
            ready = content is not None
        else:
            report, preview = mechanical_preview(
                source, request["project"], request["clearanceMm"], directory)
            content = None
            ready = True
        if request.get("workflow"):
            from monitor.pcb_flow import mechanical_programs
            sequence, programs = mechanical_programs(
                source, report["transform"], preview, request["workflow"],
                request["clearanceMm"], directory)
            report["sequence"] = sequence
            preview["paths"].extend(operation["path"] for operation in sequence
                                    if operation["kind"] == "outline")
            preview["holes"] = [{"point": point,
                                 "diameterMm": operation["diameterMm"]}
                                for operation in sequence
                                if operation["kind"] == "drilling"
                                for point in operation["points"]]
            if "isolation" in requested:
                report["sequence"].insert(0, {
                    "file": "isolation.nc", "kind": "isolation",
                    "title": request["profile"]["name"],
                    "zPreparation": "grid3", "depthMm": report["depthMm"]})
            report["material"] = request["workflow"]
            if ready:
                for name, program in programs.items():
                    (directory / name).write_text(program, encoding="ascii")
                report["operations"] = {kind: "ready" if kind in requested
                                        else "not_requested" for kind in (
                                            "isolation", "drilling", "outline")}
        (directory / "preview.json").write_text(json.dumps(preview))
        if content is not None:
            (directory / "isolation.nc").write_text(content, encoding="ascii")
        result = {"state": "ready" if ready else "blocked",
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
