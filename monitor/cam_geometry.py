# ---------------------------------------------------------------------------
# cam_geometry.py
# 2026-11-13
# - Shared board geometry and independent mechanical/isolation preparation.
# ---------------------------------------------------------------------------
"""Geometry-only CAM: no machine, serial, network or controller dependencies."""

import io
import json
import math
from pathlib import Path
import warnings
import zipfile

from gerbonara import GerberFile
from gerbonara.utils import MM
from shapely import affinity, make_valid
from shapely.geometry import GeometryCollection, LineString, Polygon, box
from shapely.ops import polygonize, unary_union

from monitor.jobs import WORD, parse_program
from monitor.profiles import check_cam_program, validate_depth

ENGINE = "bark-planar-isolation/1;gerbonara/1.6.3;shapely/2.2.0"
MARGIN = .008
TOLERANCE = .005


def polygons(shape):
    """Return only polygonal parts of a potentially mixed geometry."""
    if shape.geom_type == "Polygon":
        return [shape]
    result = []
    for child in getattr(shape, "geoms", []):
        result.extend(polygons(child))
    return result


def read_copper(filename):
    """Respect aperture-local clear features and image polarity in order."""
    image = GeometryCollection()
    with warnings.catch_warnings(record=True) as diagnostics:
        warnings.simplefilter("always")
        gerber = GerberFile.open(filename)
        if len(gerber.objects) > 50000:
            raise ValueError("Za dużo obiektów Gerber.")
        for item in gerber.objects:
            local = GeometryCollection()
            for primitive in item.to_primitives(unit=MM):
                if primitive.is_zero_size():
                    continue
                outline = primitive.to_arc_poly().approximate_arcs(
                    max_error=.001).outline
                region = make_valid(Polygon(outline))
                if primitive.polarity_dark == item.polarity_dark:
                    local = local.union(region)
                else:
                    local = local.difference(region)
            if item.polarity_dark:
                image = image.union(local)
            else:
                image = image.difference(local)
        if diagnostics:
            raise ValueError("Parser Gerber zgłosił ostrzeżenie: "
                             + str(diagnostics[0].message)[:200])
    if image.is_empty or not image.is_valid:
        raise ValueError("Niepoprawna lub pusta geometria miedzi.")
    return image


def read_archive(data, project, directory):
    """Read a bounded ZIP without extracting paths or trusting file names."""
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        entries = archive.infolist()
        names = [item.filename for item in entries]
        if len(entries) > 100 or len(set(names)) != len(names) or any(
            item.file_size > 12 * 1024 * 1024 for item in entries
        ) or sum(item.file_size for item in entries) > 32 * 1024 * 1024:
            raise ValueError("Archiwum CAM przekracza limity.")
        if any(name.startswith(("/", "\\")) or ".." in name.split("/")
               or "\\" in name for name in names):
            raise ValueError("Niedozwolona ścieżka w archiwum.")
        plan = json.loads(archive.read("copper-plan.json"))
        validation = json.loads(archive.read("validation.json"))
        readback = json.loads(archive.read("copper-readback.json"))
        if plan.get("sourceHash") != project["boardHash"] or (
            plan.get("settings", {}).get("layer") != project["side"]
        ) or validation.get("issues") != 0 or validation.get("findings"):
            raise ValueError("Pakiet nie odpowiada sprawdzonemu PCB.")
        if readback.get("findings") != []:
            raise ValueError("Pakiet nie przeszedł kontroli geometrii.")
        suffix = "-B_Cu.gbl" if project["side"] == "B.Cu" else "-F_Cu.gtl"
        copper_names = [name for name in names if name.endswith(suffix)]
        outline_names = [name for name in names
                         if name.endswith("-Edge_Cuts.gm1")]
        if len(copper_names) != 1 or len(outline_names) != 1:
            raise ValueError("Wymagana jedna warstwa i jeden obrys PCB.")
        copper_file = directory / "copper.gbr"
        copper_file.write_bytes(archive.read(copper_names[0]))
        outline_file = directory / "outline.gbr"
        outline_file.write_bytes(archive.read(outline_names[0]))
    # The board datum comes from the outline, never each operation's bounds.
    outline = GerberFile.open(outline_file)
    lines = []
    for item in outline.objects:
        item = item.converted(MM)
        if type(item).__name__ != "Line":
            raise ValueError("Ten CAM obsługuje prostokątny obrys liniowy.")
        lines.append(LineString([(item.x1, item.y1), (item.x2, item.y2)]))
    regions = list(polygonize(lines))
    if len(regions) != 1 or not regions[0].equals(box(*regions[0].bounds)):
        raise ValueError("Wymagany zamknięty prostokątny obrys PCB.")
    stock = regions[0]
    if stock.area > 40000 or stock.area < 1:
        raise ValueError("Rozmiar płytki poza zakresem CAM.")
    copper = read_copper(copper_file)
    if not stock.buffer(TOLERANCE).covers(copper):
        raise ValueError("Miedź wykracza poza obrys PCB.")
    return copper, stock


def tool_parameters(profile):
    """Only measured, fixed-depth profiles can generate production paths."""
    if not profile.get("model") or "depth" not in profile:
        raise ValueError("Wybierz skalibrowany profil ze stałą głębokością.")
    model = profile["model"]
    depth = profile["depth"]
    validate_depth(depth, model)
    diameter = model["intercept_mm"] + model["slope"] * depth
    conditions = profile["conditions"]
    if not .01 <= diameter <= 2 or not (
        1 <= conditions["plunge"] <= 100
        and 1 <= conditions["feed"] <= 300
        and 1 <= conditions["power"] <= 1000
    ) or any(not math.isfinite(value) for value in conditions.values()):
        raise ValueError("Parametry profilu poza zakresem CAM.")
    return diameter, depth, conditions


def transform_geometry(copper, stock, side):
    """One common lower-left machined-side datum; back side mirrors X."""
    x0, y0, x1, y1 = stock.bounds
    matrix = [-1, 0, 0, 1, x1, -y0] if side == "B.Cu" else (
        [1, 0, 0, 1, -x0, -y0])
    return (affinity.affine_transform(copper, matrix),
            affinity.affine_transform(stock, matrix),
            {"matrix": matrix, "side": side,
             "mirrorX": side == "B.Cu",
             "datum": "G54: lewy dolny narożnik od strony obróbki",
             "sourceOutlineBounds": list(stock.bounds)})


def contour_paths(copper, diameter):
    """Offset protected copper with a small numerical clearance budget."""
    excluded = copper.buffer(diameter / 2 + MARGIN, quad_segs=32)
    paths = []
    for region in polygons(excluded):
        for ring in [region.exterior, *region.interiors]:
            simple = LineString(ring.coords).simplify(.004)
            path = [[round(x, 5), round(y, 5)] for x, y in simple.coords]
            paths.append(path)
    return paths


def emit_program(paths, profile, clearance):
    """Emit one linear GRBL operation, with no inherited modal state."""
    diameter, depth, conditions = tool_parameters(profile)
    lines = [f"; BARK_BEETLE_PROFILE {profile['id']} "
             f"{profile['fingerprint']}", "G21", "G90", "G94", "G54",
             f"G0 Z{clearance:.5f}", f"M3 S{conditions['power']:g}",
             "G4 P2"]
    for path in paths:
        x, y = path[0]
        lines.extend([f"G0 X{x:.5f} Y{y:.5f}",
                      f"G1 Z{-depth:.5f} F{conditions['plunge']:g}"])
        for x, y in path[1:]:
            lines.append(f"G1 X{x:.5f} Y{y:.5f} "
                         f"F{conditions['feed']:g}")
        lines.append(f"G0 Z{clearance:.5f}")
    lines.extend(["M5", "M30"])
    content = "\n".join(lines) + "\n"
    program = parse_program("isolation.nc", content)
    check_cam_program(profile, program, {})
    return content, program


def emitted_paths(program):
    """Reconstruct actual rounded NC movements, independently of CAM paths."""
    position = {"X": None, "Y": None, "Z": None}
    paths = []
    motion = 0
    for line in program["lines"]:
        words = [(key, float(value)) for key, value
                 in WORD.findall(line["code"])]
        previous = dict(position)
        for key, value in words:
            if key == "G" and value in (0, 1):
                motion = int(value)
            if key in position:
                position[key] = value
        xy = any(key in "XY" for key, value in words)
        if xy and previous["Z"] is not None and previous["Z"] < 0:
            if motion != 1 or position["Z"] != previous["Z"]:
                raise ValueError("Niepoprawny przejazd w materiale.")
            paths.append(LineString([
                (previous["X"], previous["Y"]),
                (position["X"], position["Y"]) ]))
        elif xy and (position["Z"] is None or position["Z"] <= 0):
            raise ValueError("Brak wycofania przed przejazdem XY.")
    if not paths:
        raise ValueError("Program nie zawiera ścieżek izolacji.")
    return unary_union(paths)


def verify_sweep(copper, stock, program, diameter):
    """Reject copper loss, unreachable boundaries and remaining-stock shorts."""
    paths = emitted_paths(program)
    swept = paths.buffer(diameter / 2, quad_segs=32)
    loss = swept.intersection(copper.buffer(-.001)).area
    inaccessible = copper.boundary.difference(
        swept.buffer(TOLERANCE + MARGIN))
    findings = []
    if loss > .0001:
        point = swept.intersection(copper).representative_point()
        findings.append({"message": "Frez narusza chronioną miedź.",
                         "x": point.x, "y": point.y})
    if inaccessible.length > .02:
        pieces = list(getattr(inaccessible, "geoms", [inaccessible]))
        for part in sorted(pieces, key=lambda item: -item.length)[:20]:
            point = part.interpolate(.5, normalized=True)
            findings.append({"message": "Frez nie mieści się przy tej "
                             "krawędzi lub w szczelinie.",
                             "x": point.x, "y": point.y})
    remaining = polygons(stock.difference(swept))
    targets = polygons(copper)
    owners = {}
    for index, target in enumerate(targets):
        matches = [number for number, region in enumerate(remaining)
                   if region.intersection(target).area > .0001]
        if len(matches) != 1 or matches[0] in owners:
            point = target.representative_point()
            findings.append({"message": "Pozostała miedź łączy oddzielne "
                             "obszary lub rozcina ścieżkę.",
                             "x": point.x, "y": point.y})
        else:
            owners[matches[0]] = index
    return {"passed": not findings, "findings": findings[:30],
            "protectedIslands": len(targets),
            "copperLossMm2": loss,
            "inaccessibleBoundaryMm": inaccessible.length,
            "toleranceMm": TOLERANCE,
            "scope": "Płaski model 2D; bez sprawdzenia mocowania i Z."}


def mechanical_preview(data, project, clearance, directory):
    """Validate the board datum without computing or requiring V-bit paths."""
    copper, stock = read_archive(data, project, directory)
    copper, stock, transform = transform_geometry(
        copper, stock, project["side"])
    preview = {"bounds": list(stock.bounds), "paths": [],
               "copper": [[list(region.exterior.coords),
                            *[list(ring.coords) for ring in region.interiors]]
                           for region in polygons(copper)]}
    report = {"engine": ENGINE, "transform": transform,
              "clearanceMm": clearance,
              "checks": {"passed": True, "findings": [],
                         "scope": "mechanical board geometry only"},
              "operations": {"isolation": "not_requested",
                             "drilling": "not_prepared",
                             "outline": "not_prepared"}}
    return report, preview


def generate(data, project, profile, clearance, directory):
    """Return evidence and NC only if every planar and format gate passes."""
    diameter, depth, conditions = tool_parameters(profile)
    copper, stock = read_archive(data, project, directory)
    copper, stock, transform = transform_geometry(
        copper, stock, project["side"])
    paths = contour_paths(copper, diameter)
    content, program = emit_program(paths, profile, clearance)
    checks = verify_sweep(copper, stock, program, diameter)
    preview = {"bounds": list(stock.bounds), "paths": paths,
               "copper": [[list(region.exterior.coords),
                            *[list(ring.coords) for ring in region.interiors]]
                           for region in polygons(copper)]}
    report = {"engine": ENGINE, "transform": transform,
              "diameterMm": diameter, "depthMm": depth,
              "clearanceMm": clearance, "conditions": conditions,
              "numerics": {"offsetMarginMm": MARGIN,
                           "simplificationMm": .004,
                           "gerberArcErrorMm": .001},
              "checks": checks, "boundsMm": program["bounds_mm"],
              "commands": len(program["lines"]),
              "operations": {"isolation": "ready" if checks["passed"]
                             else "blocked", "drilling": "not_prepared",
                             "outline": "not_prepared"}}
    return report, preview, content if checks["passed"] else None

# ---------------------------------------------------------------------------
# end of file
# ---------------------------------------------------------------------------
