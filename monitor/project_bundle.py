# ---------------------------------------------------------------------------
# project_bundle.py
# 2026-11-13
# - Validate revision-bound Tractor stage files and semantic THT holes.
# ---------------------------------------------------------------------------
"""Project packages contain CAD geometry, never machine commands or profiles."""

import hashlib
import io
import json
import math
from pathlib import PurePosixPath
import zipfile

DATUM = "KiCad absolute board datum; shared copper, drills and outline"


def finite(value, low=-10000, high=10000):
    """Reject JSON booleans and non-finite coordinates before geometry use."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("Niepoprawna współrzędna pakietu PCB.")
    if not math.isfinite(value) or not low <= value <= high:
        raise ValueError("Współrzędna pakietu PCB poza zakresem.")
    return float(value)


def read_bundle(data, project, required=False):
    """Normalize broken/encrypted ZIP input to the public validation error."""
    try:
        return _read_bundle(data, project, required)
    except (zipfile.BadZipFile, RuntimeError, UnicodeError) as error:
        raise ValueError("Uszkodzona lub zaszyfrowana paczka PCB.") from error


def _read_bundle(data, project, required):
    """Verify stage hashes/source identity and preserve legacy ZIP reads."""
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        if not required:
            return None
        raise ValueError("Brak poprawnej paczki projektu PCB.") from None
    with archive:
        if "machining-project.json" not in archive.namelist():
            if not required:
                return None
            raise ValueError("Wyślij ponownie projekt z aktualnego Tractora.")
        names = archive.namelist()
        if len(names) > 100 or len(set(names)) != len(names):
            raise ValueError("Powtórzone pliki lub zbyt duża paczka PCB.")
        for item in archive.infolist():
            name = PurePosixPath(item.filename)
            if name.is_absolute() or ".." in name.parts or (
                "\\" in item.filename or item.file_size > 5 * 1024 * 1024
            ):
                raise ValueError("Niedozwolony plik w paczce PCB.")
        if sum(item.file_size for item in archive.infolist()) > 20 * 1024**2:
            raise ValueError("Paczka PCB przekracza limit danych.")
        manifest = json.loads(archive.read("machining-project.json"))
        if not isinstance(manifest, dict) or (
            manifest.get("schemaVersion") != 1 or
            manifest.get("sourceHash") != project["boardHash"] or
            manifest.get("side") != project["side"] or
            manifest.get("datum") != DATUM
        ):
            raise ValueError("Paczka etapów nie odpowiada wersji PCB.")
        stages = manifest.get("stages")
        if not isinstance(stages, dict) or set(stages) != {
            "isolation", "drilling", "outline"
        }:
            raise ValueError("Brak trzech etapów w paczce projektu.")
        stage_data = {}
        for kind, record in stages.items():
            if not isinstance(record, dict):
                raise ValueError("Niepoprawny opis etapu PCB.")
            name = record.get("file")
            if name not in names or not isinstance(name, str):
                raise ValueError("Brak pliku etapu PCB.")
            expected = {"isolation": ".gbl" if project["side"] == "B.Cu"
                        else ".gtl", "outline": "-Edge_Cuts.gm1",
                        "drilling": "tht-holes.json"}[kind]
            if not name.endswith(expected):
                raise ValueError("Plik nie odpowiada rodzajowi etapu PCB.")
            content = archive.read(name)
            if hashlib.sha256(content).hexdigest() != record.get("sha256"):
                raise ValueError("Zmieniony plik etapu PCB.")
            stage_data[kind] = content
        hole_data = json.loads(stage_data["drilling"])
        if not isinstance(hole_data, dict) or (
            hole_data.get("schemaVersion") != 1 or
            hole_data.get("sourceHash") != project["boardHash"] or
            hole_data.get("coordinateSpace") != "gerber-mm"
        ):
            raise ValueError("Wiercenia nie odpowiadają wersji PCB.")
        holes = hole_data.get("holes")
        unsupported = hole_data.get("unsupported")
        if not isinstance(holes, list) or len(holes) > 1000 or (
            not isinstance(unsupported, list) or len(unsupported) > 1000
        ):
            raise ValueError("Niepoprawny wykaz otworów THT.")
        identities = set()
        checked = []
        for hole in holes:
            if not isinstance(hole, dict) or hole.get("role") != "tht":
                raise ValueError("Wykaz THT zawiera inny rodzaj otworu.")
            identity = hole.get("id")
            if not isinstance(identity, str) or not 1 <= len(identity) <= 100:
                raise ValueError("Brak identyfikatora otworu THT.")
            if identity in identities:
                raise ValueError("Powtórzony otwór THT.")
            identities.add(identity)
            checked.append({"id": identity,
                "x": finite(hole.get("x")), "y": finite(hole.get("y")),
                "diameterMm": finite(hole.get("diameterMm"), .3, 4)})
        bounds = manifest.get("boundsMm")
        if not isinstance(bounds, list) or len(bounds) != 4:
            raise ValueError("Brak wymiarów projektu PCB.")
        bounds = [finite(value) for value in bounds]
        if bounds[2] <= bounds[0] or bounds[3] <= bounds[1]:
            raise ValueError("Niepoprawny obrys projektu PCB.")
        return {"manifest": manifest, "holes": checked,
                "unsupported": unsupported, "boundsMm": bounds}


def bundle_summary(data, project):
    """Expose small stage capabilities without source files or credentials."""
    bundle = read_bundle(data, project)
    if bundle is None:
        return {"version": 0, "stages": {
            "isolation": {"available": True},
            "outline": {"available": True},
            "drilling": {"available": False, "reason":
                "Wyślij ponownie projekt z Tractora, aby rozpoznać THT."}}}
    holes = bundle["holes"]
    return {"version": 1, "boundsMm": bundle["boundsMm"],
            "stages": {"isolation": {"available": True},
                "outline": {"available": True},
                "drilling": {"available": bool(holes) and not bundle[
                    "unsupported"], "count": len(holes),
                    "diametersMm": sorted({h["diameterMm"] for h in holes}),
                    "reason": "Nietypowe otwory wymagają osobnej obróbki." if (
                        bundle["unsupported"]) else "" if holes else (
                            "Projekt nie zawiera otworów THT.")}},
            "holes": holes}

# ---------------------------------------------------------------------------
# end of file
# ---------------------------------------------------------------------------
