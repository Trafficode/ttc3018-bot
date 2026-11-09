# ---------------------------------------------------------------------------
# pcb_flow.py
# 2026-11-09
# - Validated material settings and linear drill/retained-outline operations.
# ---------------------------------------------------------------------------
"""Mechanical CAM shares the isolation transform, never a V-bit model."""

import io
import math
import re
import warnings
import zipfile

from gerbonara import ExcellonFile
from gerbonara.utils import MM

from monitor.jobs import parse_program


def number(data, name, low, high):
    """Require an explicit finite JSON number within a physical input range."""
    value = data.get(name)
    if isinstance(value, bool) or not isinstance(value, (int, float)) or (
        not math.isfinite(value) or not low <= value <= high
    ):
        raise ValueError(f"{name}: wymagana liczba {low}–{high}.")
    return float(value)


def validate_flow(data):
    """Capture material and separate drill/end-mill parameters, no defaults."""
    if not isinstance(data, dict):
        raise ValueError("Wprowadź parametry wykonania PCB.")
    result = {
        "thicknessMm": number(data, "thicknessMm", .3, 3),
        "skinMm": number(data, "skinMm", .15, .5),
        "uncertaintyMm": number(data, "uncertaintyMm", .01, .2),
        "breakthroughMm": number(data, "breakthroughMm", .05, 1),
        "stepDownMm": number(data, "stepDownMm", .02, .5),
        "cuttingLengthMm": number(data, "cuttingLengthMm", .5, 15),
        "drillFeed": number(data, "drillFeed", 1, 100),
        "drillPower": number(data, "drillPower", 1, 1000),
        "drillPointAngleDeg": number(data, "drillPointAngleDeg", 60, 150),
        "backingMm": number(data, "backingMm", 1, 50),
        "millFeed": number(data, "millFeed", 1, 300),
        "millPlunge": number(data, "millPlunge", 1, 100),
        "millPower": number(data, "millPower", 1, 1000),
        "millDiameterMm": number(data, "millDiameterMm", 1, 1),
        "tabWidthMm": number(data, "tabWidthMm", 2, 6),
        "tabHeightMm": number(data, "tabHeightMm", .2, .8)}
    retention = data.get("retention")
    if retention not in ("skin", "tabs"):
        raise ValueError("Wybierz cienką warstwę lub mostki.")
    result["retention"] = retention
    retained = result["skinMm"] if retention == "skin" else (
        result["tabHeightMm"])
    if result["skinMm"] <= result["uncertaintyMm"] or (
        result["thicknessMm"] <= retained
    ):
        raise ValueError("Warstwa/mostki muszą być cieńsze od laminatu; "
                         "warstwa musi przekraczać budżet błędu.")
    depth = result["thicknessMm"] - result["skinMm"]
    if retention == "tabs":
        depth = result["thicknessMm"] + result["breakthroughMm"]
    if result["cuttingLengthMm"] < depth:
        raise ValueError("Część robocza frezu jest krótsza niż głębokość.")
    if data.get("confirmedSetup") is not True:
        raise ValueError("Potwierdź podkład, mocowanie i punkty pomiaru.")
    result["confirmedSetup"] = True
    return result


def startup(clearance, power):
    """One explicit tool, work coordinate system and spindle envelope."""
    return ["G21", "G90", "G94", "G54", f"G0 Z{clearance:g}",
            f"M3 S{power:g}", "G4 P2"]


def checked_program(lines, name):
    """Validate complete output before returning any selectable artifact."""
    content = "\n".join([*lines, "M5", "M30"]) + "\n"
    parsed = parse_program(name, content)
    return content, {"file": name, "commands": len(parsed["lines"]),
                     "boundsMm": parsed["bounds_mm"]}


def drill_groups(data, transform, directory):
    """Read every PTH/NPTH round hole; slots fail rather than disappear."""
    groups = {}
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        names = [name for name in archive.namelist()
                 if name.endswith(("-PTH.drl", "-NPTH.drl"))]
        if not names:
            raise ValueError("Brak źródłowych plików wierceń.")
        for index, name in enumerate(names):
            filename = directory / f"drills-{index}.drl"
            filename.write_bytes(archive.read(name))
            with warnings.catch_warnings(record=True) as diagnostics:
                warnings.simplefilter("always")
                source = ExcellonFile.open(filename)
                # KiCad places its explicit absolute-mode command after the
                # header. Gerbonara accepts the mode but reports its location.
                # Permit only this exact known diagnostic, never a mode change.
                unsafe = [value for value in diagnostics if not re.search(
                    r'"G90": G90 header statement found after end of header$',
                    str(value.message))]
                if unsafe:
                    raise ValueError("Ostrzeżenie parsera wierceń: "
                                     + str(unsafe[0].message)[:150])
            for item in source.objects:
                item = item.converted(MM)
                if type(item).__name__ != "Flash":
                    raise ValueError("Otwory podłużne wymagają osobnej "
                                     "operacji; nie pomijam ich.")
                diameter = round(item.tool.unit.convert_to(
                    MM, item.tool.diameter), 6)
                if not .3 <= diameter <= 4:
                    raise ValueError("Średnica wiertła poza 0,3–4 mm.")
                a, b, c, d, tx, ty = transform["matrix"]
                point = [a * item.x + b * item.y + tx,
                         c * item.x + d * item.y + ty]
                groups.setdefault(diameter, []).append(point)
    if sum(map(len, groups.values())) > 1000:
        raise ValueError("Za dużo otworów w zleceniu.")
    if len(groups) > 32:
        raise ValueError("Zlecenie przekracza limit 32 średnic wierteł.")
    return groups


def mechanical_programs(data, transform, preview, settings, clearance,
                        directory):
    """Generate drilling per diameter and a rectangular outside profile."""
    operations = []
    contents = {}
    depth = settings["thicknessMm"] + settings["breakthroughMm"]
    for index, (diameter, points) in enumerate(sorted(
        drill_groups(data, transform, directory).items()
    )):
        x0, y0, x1, y1 = preview["bounds"]
        if any(not (x0 + diameter/2 <= x <= x1 - diameter/2 and
                    y0 + diameter/2 <= y <= y1 - diameter/2)
               for x, y in points):
            raise ValueError("Otwór wychodzi poza gotowy obrys PCB.")
        name = f"drill-{index:02d}.nc"
        tip = diameter / (2 * math.tan(math.radians(
            settings["drillPointAngleDeg"] / 2)))
        drill_depth = depth + tip
        if tip + settings["breakthroughMm"] + .5 > settings["backingMm"]:
            raise ValueError("Podkład za cienki na pełne przejście wiertła.")
        lines = startup(clearance, settings["drillPower"])
        for x, y in points:
            lines.extend([f"G0 X{x:.5f} Y{y:.5f}",
                          f"G1 Z{-drill_depth:.5f} "
                          f"F{settings['drillFeed']:g}",
                          f"G0 Z{clearance:g}"])
        content, record = checked_program(lines, name)
        contents[name] = content
        operations.append({**record, "kind": "drilling",
                           "title": f"Wiertło Ø{diameter:g} mm",
                           "diameterMm": diameter, "holes": len(points),
                           "points": points, "depthMm": drill_depth,
                           "breakthroughMm": settings["breakthroughMm"],
                           "uncertaintyMm": settings["uncertaintyMm"],
                           "zPreparation": "point"})
    x0, y0, x1, y1 = preview["bounds"]
    radius = settings["millDiameterMm"] / 2
    x0, y0, x1, y1 = x0-radius, y0-radius, x1+radius, y1+radius
    if min(x1-x0, y1-y0) <= settings["tabWidthMm"] + 2:
        raise ValueError("Obrys jest za mały dla wybranych mostków.")
    final_depth = settings["thicknessMm"] - settings["skinMm"]
    if settings["retention"] == "tabs":
        final_depth = depth
    passes = math.ceil(final_depth / settings["stepDownMm"])
    lines = startup(clearance, settings["millPower"])
    corners = [(x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0)]
    for level in range(1, passes + 1):
        cut = min(final_depth, level * settings["stepDownMm"])
        lines.extend([f"G0 X{x0:.5f} Y{y0:.5f}",
                      f"G1 Z{-cut:.5f} F{settings['millPlunge']:g}"])
        for start, end in zip(corners, corners[1:]):
            points = [end]
            tab_depth = settings["thicknessMm"] - settings["tabHeightMm"]
            if settings["retention"] == "tabs" and cut > tab_depth:
                length = math.dist(start, end)
                fractions = [.5-settings["tabWidthMm"]/length/2,
                             .5+settings["tabWidthMm"]/length/2]
                points = [[start[i] + f*(end[i]-start[i]) for i in (0, 1)]
                          for f in fractions] + [end]
            for position, (x, y) in enumerate(points):
                lines.append(f"G1 X{x:.5f} Y{y:.5f} "
                             f"F{settings['millFeed']:g}")
                if len(points) == 3 and position in (0, 1):
                    target = tab_depth if position == 0 else cut
                    lines.append(f"G1 Z{-target:.5f} "
                                 f"F{settings['millPlunge']:g}")
        lines.append(f"G0 Z{clearance:g}")
    content, record = checked_program(lines, "outline.nc")
    contents["outline.nc"] = content
    operations.append({**record, "kind": "outline", "title": "Frez Ø1 mm",
                       "diameterMm": 1, "depthMm": final_depth,
                       "passes": passes, "retention": settings["retention"],
                       "path": corners, "zPreparation": "grid3"})
    return operations, contents

# ---------------------------------------------------------------------------
# end of file
# ---------------------------------------------------------------------------
