# ---------------------------------------------------------------------------
# pcb_flow.py
# 2026-11-13
# - Simple mechanical profiles with optional outline passes and tab width.
# ---------------------------------------------------------------------------
"""Mechanical CAM shares the isolation transform, never a V-bit model."""

import io
import math
import re
import warnings
import zipfile

from monitor.jobs import parse_program

FLOW_LIMITS = {
    "thicknessMm": (.3, 3), "skinMm": (.15, .5),
    "uncertaintyMm": (.01, .2), "breakthroughMm": (.05, 1),
    "stepDownMm": (.02, .5), "cuttingLengthMm": (.5, 15),
    "drillFeed": (1, 100), "drillPower": (1, 1000),
    "drillPointAngleDeg": (60, 150), "backingMm": (1, 50),
    "millFeed": (1, 300), "millPlunge": (1, 100),
    "millPower": (1, 1000), "millDiameterMm": (.5, 3),
    "tabWidthMm": (2, 6), "tabHeightMm": (.2, .8)}

OPERATION_ORDER = ("isolation", "drilling", "outline")
DRILL_POWER = 1000
OUTLINE_POWER = 1000
OUTLINE_STEP_DOWN_MM = .2
TOOL_FIELDS = {
    "drilling": ("drillFeed", "drillPower", "drillPointAngleDeg",
                 "backingMm", "breakthroughMm", "uncertaintyMm"),
    "outline": ("millFeed", "millPlunge", "millPower", "millDiameterMm",
                "stepDownMm", "cuttingLengthMm", "backingMm",
                "breakthroughMm", "uncertaintyMm"),
}

def number(data, name, low, high):
    """Require an explicit finite JSON number within a physical input range."""
    value = data.get(name)
    if isinstance(value, bool) or not isinstance(value, (int, float)) or (
        not math.isfinite(value) or not low <= value <= high
    ):
        raise ValueError(f"{name}: wymagana liczba {low}–{high}.")
    return float(value)


def selected_operations(data):
    """Keep a unique, canonical sequence; old workflows retain all stages."""
    values = data.get("operations", list(OPERATION_ORDER))
    if (not isinstance(values, list) or not values
            or any(value not in OPERATION_ORDER for value in values)
            or len(values) != len(set(values))):
        raise ValueError("Wybierz poprawny zakres obróbki PCB.")
    return [kind for kind in OPERATION_ORDER if kind in values]


def validate_tool_values(data, kind):
    """Validate only the selected tool; never require another tool's feed."""
    if kind not in TOOL_FIELDS or not isinstance(data, dict):
        raise ValueError("Niepoprawny rodzaj profilu narzędzia.")
    if kind == "outline" and data.get("outlineDepthMode") == "remaining":
        return validate_simple_outline(data)
    fields = TOOL_FIELDS[kind]
    simple_drilling = kind == "drilling" and "drillOverrunMm" in data
    if simple_drilling:
        fields = ("drillFeed",)
    result = {key: number(data, key, *FLOW_LIMITS[key]) for key in fields}
    if simple_drilling:
        result["drillOverrunMm"] = number(data, "drillOverrunMm", .05, 5)
    result["clearanceMm"] = number(data, "clearanceMm", 1, 10)
    if kind == "drilling":
        diameter = number(data, "drillDiameterMm", 0, 4)
        if diameter != 0 and diameter < .3:
            raise ValueError("Wiertło: wybierz średnicę 0,3–4 mm lub z pliku.")
        result["drillDiameterMm"] = diameter
    else:
        retention = data.get("retention")
        if retention not in ("skin", "tabs", "through"):
            raise ValueError("Wybierz sposób oddzielenia PCB.")
        result["retention"] = retention
        if retention == "skin":
            result["skinMm"] = number(data, "skinMm", *FLOW_LIMITS["skinMm"])
            if result["skinMm"] <= result["uncertaintyMm"]:
                raise ValueError("Pozostawiona warstwa musi przekraczać "
                                 "budżet błędu grubości i Z.")
        if retention == "tabs":
            for key in ("tabWidthMm", "tabHeightMm"):
                result[key] = number(data, key, *FLOW_LIMITS[key])
            if result["tabWidthMm"] <= result["millDiameterMm"]:
                raise ValueError("Mostek musi być szerszy od frezu.")
    return result


def validate_simple_outline(data):
    """Retained stock is explicit; optional overrides never need filling in."""
    result = {key: number(data, key, *FLOW_LIMITS[key]) for key in (
        "millDiameterMm", "millFeed", "millPlunge")}
    result["outlineDepthMode"] = "remaining"
    result["clearanceMm"] = number(data, "clearanceMm", 1, 10)
    retention = data.get("retention")
    if retention not in ("skin", "tabs", "through"):
        raise ValueError("Wybierz sposób oddzielenia PCB.")
    result["retention"] = retention
    if retention != "through":
        result["remainingMm"] = number(data, "remainingMm", .05, 3)
    if retention != "skin":
        result["millOverrunMm"] = number(data, "millOverrunMm", .05, 5)
    if "stepDownMm" in data:
        result["stepDownMm"] = number(data, "stepDownMm",
                                      *FLOW_LIMITS["stepDownMm"])
    if retention == "tabs" and "tabWidthMm" in data:
        result["tabWidthMm"] = number(data, "tabWidthMm",
                                      *FLOW_LIMITS["tabWidthMm"])
        if result["tabWidthMm"] <= result["millDiameterMm"]:
            raise ValueError("Mostek musi być szerszy od frezu.")
    return result


def resolved_outline_settings(settings):
    """Resolve engine defaults without persisting fake tool/backing lengths."""
    if settings.get("outlineDepthMode") != "remaining":
        return settings
    return {**settings, "millPower": OUTLINE_POWER,
            "stepDownMm": settings.get("stepDownMm", OUTLINE_STEP_DOWN_MM),
            "tabWidthMm": settings.get("tabWidthMm", max(
                3, settings["millDiameterMm"] + 2)),
            "skinMm": settings.get("remainingMm", 0),
            "tabHeightMm": settings.get("remainingMm", 0),
            "breakthroughMm": settings.get("millOverrunMm", 0)}


def validate_selected_flow(data):
    """Freeze independent tools with one measured material thickness."""
    operations = selected_operations(data)
    if data.get("confirmedSetup") is not True:
        raise ValueError("Potwierdź podkład, mocowanie i punkty pomiaru.")
    result = {"operations": operations, "confirmedSetup": True,
              "thicknessMm": number(data, "thicknessMm", .3, 3),
              "operationSettings": {}}
    incoming = data.get("operationSettings")
    if not isinstance(incoming, dict) or set(incoming) != (
        set(operations) - {"isolation"}
    ):
        raise ValueError("Wybierz profil dla każdej operacji mechanicznej.")
    for kind in operations:
        if kind == "isolation":
            continue
        values = validate_tool_values(incoming[kind], kind)
        if kind == "outline":
            resolved = resolved_outline_settings(values)
            retention = resolved["retention"]
            retained = resolved.get("skinMm", resolved.get("tabHeightMm", 0))
            if result["thicknessMm"] <= retained:
                raise ValueError("Warstwa lub mostki muszą być cieńsze od PCB.")
            depth = result["thicknessMm"] - retained
            if retention != "skin":
                depth = result["thicknessMm"] + resolved["breakthroughMm"]
            if values.get("outlineDepthMode") != "remaining":
                if values["cuttingLengthMm"] < depth:
                    raise ValueError("Część robocza frezu jest za krótka.")
                if values["breakthroughMm"] + .5 > values["backingMm"]:
                    raise ValueError("Podkład za cienki na wycięcie PCB.")
            if retention == "through":
                if data.get("confirmedThroughCut") is not True:
                    raise ValueError("Potwierdź mocowanie PCB przy cięciu "
                                     "na wylot bez mostków.")
                result["confirmedThroughCut"] = True
            result.update({key: resolved[key] for key in (
                "retention", "skinMm", "tabHeightMm"
            ) if key in resolved})
        result["operationSettings"][kind] = values
    return result


def validate_flow(data):
    """Capture material and separate drill/end-mill parameters, no defaults."""
    if not isinstance(data, dict):
        raise ValueError("Wprowadź parametry wykonania PCB.")
    if "operationSettings" in data:
        return validate_selected_flow(data)
    result = {key: number(data, key, low, high)
              for key, (low, high) in FLOW_LIMITS.items()}
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
    from gerbonara import ExcellonFile
    from gerbonara.utils import MM
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


def drilling_programs(data, transform, preview, settings, clearance, directory):
    """Preserve source hole diameters and use only the drilling profile."""
    operations = []
    contents = {}
    simple = "drillOverrunMm" in settings
    overrun = settings["drillOverrunMm"] if simple else (
        settings["breakthroughMm"])
    depth = settings["thicknessMm"] + overrun
    groups = drill_groups(data, transform, directory)
    if not groups:
        raise ValueError("Plik PCB nie zawiera otworów do wiercenia.")
    selected = settings.get("drillDiameterMm", 0)
    if selected and any(abs(selected - value) > .000001 for value in groups):
        raise ValueError("Średnica profilu nie odpowiada otworom PCB. "
                         "Wybierz średnicę według pliku lub zgodny profil.")
    for index, (diameter, points) in enumerate(sorted(groups.items())):
        x0, y0, x1, y1 = preview["bounds"]
        if any(not (x0 + diameter/2 <= x <= x1 - diameter/2 and
                    y0 + diameter/2 <= y <= y1 - diameter/2)
               for x, y in points):
            raise ValueError("Otwór wychodzi poza gotowy obrys PCB.")
        name = f"drill-{index:02d}.nc"
        drill_depth = depth
        power = DRILL_POWER
        details = {"drillOverrunMm": overrun}
        if not simple:
            # Old recipes retain their original meaning until explicitly edited.
            tip = diameter / (2 * math.tan(math.radians(
                settings["drillPointAngleDeg"] / 2)))
            drill_depth += tip
            if tip + overrun + .5 > settings["backingMm"]:
                raise ValueError("Podkład za cienki na pełne przejście wiertła.")
            power = settings["drillPower"]
            details = {"breakthroughMm": overrun,
                       "uncertaintyMm": settings["uncertaintyMm"]}
        lines = startup(clearance, power)
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
                           **details,
                           "zPreparation": "point"})
    return operations, contents


def outline_program(preview, settings, clearance):
    """Offset by the actual end-mill radius; keep the selected retention."""
    settings = resolved_outline_settings(settings)
    operations = []
    contents = {}
    x0, y0, x1, y1 = preview["bounds"]
    radius = settings["millDiameterMm"] / 2
    x0, y0, x1, y1 = x0-radius, y0-radius, x1+radius, y1+radius
    if settings["retention"] == "tabs" and (
        min(x1-x0, y1-y0) <= settings["tabWidthMm"] + 2
    ):
        raise ValueError("Obrys jest za mały dla wybranych mostków.")
    final_depth = settings["thicknessMm"] + settings["breakthroughMm"]
    if settings["retention"] == "skin":
        final_depth = settings["thicknessMm"] - settings["skinMm"]
    passes = math.ceil(final_depth / settings["stepDownMm"])
    lines = startup(clearance, settings["millPower"])
    corners = [(x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0)]
    for level in range(1, passes + 1):
        cut = min(final_depth, level * settings["stepDownMm"])
        lines.extend([f"G0 X{x0:.5f} Y{y0:.5f}",
                      f"G1 Z{-cut:.5f} F{settings['millPlunge']:g}"])
        for start, end in zip(corners, corners[1:]):
            points = [end]
            tab_depth = settings["thicknessMm"] - settings.get(
                "tabHeightMm", 0)
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
    diameter = settings["millDiameterMm"]
    operations.append({**record, "kind": "outline",
                       "title": f"Frez Ø{diameter:g} mm",
                       "diameterMm": diameter, "depthMm": final_depth,
                       "passes": passes, "retention": settings["retention"],
                       "stepDownMm": settings["stepDownMm"],
                       **({"tabWidthMm": settings["tabWidthMm"]}
                          if settings["retention"] == "tabs" else {}),
                       "path": corners, "zPreparation": "grid3"})
    return operations, contents


def mechanical_programs(data, transform, preview, settings, clearance,
                        directory):
    """Generate exactly the requested operations with separate tool values."""
    operations = []
    contents = {}
    requested = selected_operations(settings)
    for kind in ("drilling", "outline"):
        if kind not in requested:
            continue
        values = {**settings, **settings.get(
            "operationSettings", {}).get(kind, {})}
        height = values.get("clearanceMm", clearance)
        if kind == "drilling":
            records, programs = drilling_programs(
                data, transform, preview, values, height, directory)
        else:
            records, programs = outline_program(preview, values, height)
        operations.extend(records)
        contents.update(programs)
    return operations, contents

# ---------------------------------------------------------------------------
# end of file
# ---------------------------------------------------------------------------
