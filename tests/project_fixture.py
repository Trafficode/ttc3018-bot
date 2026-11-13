# ---------------------------------------------------------------------------
# project_fixture.py
# 2026-11-13
# - Revision-bound project packages for hardware-free import/CAM tests.
# ---------------------------------------------------------------------------
"""Known board coordinates match the existing real Gerber fixture."""

import hashlib
import io
import json
import zipfile

from test_cam import archive
from monitor.project_bundle import DATUM


def project_archive(holes=None, unsupported=None):
    """Supply semantic component holes separately from legacy drill files."""
    if holes is None:
        holes = [{"id": "j1-1", "role": "tht", "x": 2, "y": 3,
                  "diameterMm": .8}, {"id": "j2-1", "role": "tht",
                  "x": 6, "y": 7, "diameterMm": 1.2}]
    with zipfile.ZipFile(io.BytesIO(archive())) as source:
        files = {name: source.read(name) for name in source.namelist()}
    # This file deliberately includes a via-sized hole. New jobs must ignore it.
    files["fixture-PTH.drl"] = (
        b"M48\nMETRIC\nT1C0.4\n%\nG90\nT1\nX5.0Y5.0\nM30\n")
    files["tht-holes.json"] = json.dumps({"schemaVersion": 1,
        "sourceHash": "a" * 64, "coordinateSpace": "gerber-mm",
        "holes": holes, "unsupported": unsupported or []}).encode()
    stages = {}
    for kind, name in (("isolation", "fixture-B_Cu.gbl"),
                       ("outline", "fixture-Edge_Cuts.gm1"),
                       ("drilling", "tht-holes.json")):
        stages[kind] = {"file": name,
                       "sha256": hashlib.sha256(files[name]).hexdigest()}
    files["machining-project.json"] = json.dumps({"schemaVersion": 1,
        "sourceHash": "a" * 64, "side": "B.Cu", "datum": DATUM,
        "boundsMm": [0, 0, 20, 20], "stages": stages}).encode()
    return zip_files(files)


def zip_files(files):
    """Build an in-memory source package without extracting client paths."""
    result = io.BytesIO()
    with zipfile.ZipFile(result, "w") as archive:
        for name, data in files.items():
            archive.writestr(name, data)
    return result.getvalue()

# ---------------------------------------------------------------------------
# end of file
# ---------------------------------------------------------------------------
