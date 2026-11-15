# ---------------------------------------------------------------------------
# cam_geometry.py
# 2026-11-13
# - Shared board geometry and independent mechanical/isolation preparation.
# ---------------------------------------------------------------------------
"""Geometry-only CAM: no machine, serial, network or controller dependencies."""

import io
import hashlib
import json
import math
import random
from pathlib import Path
import warnings
import zipfile

from gerbonara import GerberFile
from gerbonara.utils import MM
from shapely import affinity, make_valid, set_precision, voronoi_polygons
from shapely.geometry import GeometryCollection, LineString, MultiPoint, Polygon, box
from shapely.ops import linemerge, polygonize, unary_union

from monitor.jobs import WORD, parse_program
from monitor.profiles import check_cam_program, validate_depth
from monitor.isolation import validate_isolation_passes

ENGINE = "bark-planar-isolation/1;gerbonara/1.6.3;shapely/2.2.0"
MARGIN = .008
TOLERANCE = .005
NC_GRID = .00001


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
        findings = validation.get("findings")
        informational = {"silk_overlap", "silk_over_copper", "silk_edge_clearance"}
        if plan.get("sourceHash") != project["boardHash"] or (
            plan.get("settings", {}).get("layer") != project["side"]
        ):
            raise ValueError("Pakiet nie odpowiada sprawdzonemu PCB.")
        if type(validation.get("issues")) is not int or validation["issues"] != 0 or not isinstance(findings, list) or any(
            not isinstance(item, dict) or item.get("informational") is not True
            or item.get("type") not in informational or item.get("severity") != "warning"
            for item in findings
        ):
            raise ValueError("Pakiet zawiera błędy blokujące produkcję PCB.")
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


def trimmed_contour_paths(copper, diameter):
    """Share tight gaps at their medial line instead of merging tool offsets.

    Voronoi territories belong to original connected copper islands. The
    actual cutter may enter both islands; its emitted sweep is checked below.
    This is a planar candidate, never permission to start a machine.
    """
    targets = polygons(copper)
    if len(targets) < 2 or len(targets) > 256:
        raise ValueError("Zwężenie padów wymaga 2–256 oddzielnych obszarów miedzi.")
    sites = {}
    for owner, target in enumerate(targets):
        for ring in [target.exterior, *target.interiors]:
            for x, y in ring.segmentize(.05).coords:
                point = (round(x, 9), round(y, 9))
                if point in sites and sites[point] != owner:
                    raise ValueError("Stykające się obszary miedzi wymagają poprawy projektu.")
                sites[point] = owner
        if len(sites) > 30000:
            raise ValueError("Zbyt złożony layout do zwężania padów.")
    # Break exact collinear/cocircular degeneracies deterministically. GEOS
    # can otherwise omit cell fragments for regular rows of boundary sites.
    # The perturbation is only one NC grid unit, far below MARGIN/TOLERANCE.
    jitter = random.Random(0)
    points = [(x + jitter.uniform(-NC_GRID, NC_GRID),
               y + jitter.uniform(-NC_GRID, NC_GRID)) for x, y in sites]
    cells = list(voronoi_polygons(MultiPoint(points), ordered=True).geoms)
    if len(cells) != len(sites):
        raise ValueError("Nie udało się wyznaczyć środka ciasnych szczelin.")
    groups = [[] for _ in targets]
    for cell, owner in zip(cells, sites.values()):
        groups[owner].append(set_precision(make_valid(cell), .0000001))
    boundaries = []
    for target, group in zip(targets, groups):
        # Overlay rounding can leave nanometre-wide cracks between cells of
        # the SAME owner. Their boundaries become real cutter plunges into
        # pads. Collapse these seams on the NC coordinate grid before taking
        # a boundary; the grid is far below the geometric tolerance.
        territory = unary_union(group).buffer(NC_GRID).buffer(-NC_GRID)
        territory = set_precision(territory, NC_GRID)
        # Voronoi overlay can also leave bounded voids with no generating
        # site. A real hole in an owner's territory must enclose copper of
        # another owner (e.g. a pad inside a ground pour). Preserve those.
        other = copper.difference(target)
        territory = unary_union([
            Polygon(region.exterior, [ring.coords for ring in region.interiors
                    if Polygon(ring).intersects(other)])
            for region in polygons(territory)])
        expanded = target.buffer(diameter/2 + MARGIN, quad_segs=32)
        boundaries.append(expanded.intersection(territory).boundary)
    network = unary_union(boundaries)
    if network.geom_type != "LineString":
        network = linemerge(network)
    lines = [network] if network.geom_type == "LineString" else list(network.geoms)
    paths = []
    for line in lines:
        if line.length < .001:
            continue
        path = [[round(x, 5), round(y, 5)] for x, y in line.simplify(.002).coords]
        if len(set(map(tuple, path))) > 1:
            paths.append(path)
    return paths


def outward_isolation_paths(copper, diameter):
    """Offset the second lane away from ALL original copper.

    The first lane is at d/2 + margin, the second at d + margin: a d/2
    stepover. Unioning the expanded copper suppresses lanes where adjacent
    lands leave insufficient room, including inside holes. Never move the
    original lane or create an inward lane around a clipped medial line.
    """
    return contour_paths(copper, 2 * diameter)


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


def verify_sweep(copper, stock, program, diameter, *, allow_loss=False):
    """Reject copper loss, unreachable boundaries and remaining-stock shorts."""
    paths = emitted_paths(program)
    swept = paths.buffer(diameter / 2, quad_segs=32)
    loss = swept.intersection(copper.buffer(-.001)).area
    inaccessible = copper.boundary.difference(
        swept.buffer(TOLERANCE + MARGIN))
    findings, notices = [], []
    # Pad trimming permits the cutter footprint to overlap copper from a
    # genuine gap. It never permits a centreline to drill across a copper land.
    intrusion = paths.intersection(copper.buffer(-TOLERANCE))
    if intrusion.length > TOLERANCE:
        point = intrusion.representative_point()
        findings.append({"message": "Środek przejazdu przecina chronioną miedź.",
                         "x": point.x, "y": point.y})
    if loss > .0001:
        point = swept.intersection(copper).representative_point()
        (notices if allow_loss else findings).append({
            "message": "Zwężenie padów i ścieżek: frez usuwa część projektowanej miedzi.",
            "x": point.x, "y": point.y} if allow_loss else {
            "message": "Frez narusza chronioną miedź.", "x": point.x, "y": point.y})
    if inaccessible.length > .02:
        pieces = list(getattr(inaccessible, "geoms", [inaccessible]))
        for part in sorted(pieces, key=lambda item: -item.length)[:20]:
            point = part.interpolate(.5, normalized=True)
            (notices if allow_loss else findings).append({"message": "Frez nie mieści się przy tej "
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
            "warnings": notices[:30],
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


def generate(data, project, profile, clearance, directory, *, allow_pad_trim=False,
             isolation_passes=1):
    """Return evidence and NC only if every planar and format gate passes."""
    diameter, depth, conditions = tool_parameters(profile)
    passes = validate_isolation_passes(isolation_passes)
    band_width = diameter * (1.5 if passes == 2 else 1)
    copper, stock = read_archive(data, project, directory)
    copper, stock, transform = transform_geometry(
        copper, stock, project["side"])
    # Solve the normal single-pass operation first. Widening may not change
    # that operation's cutter geometry, paths or accepted copper loss.
    paths = contour_paths(copper, diameter)
    content, program = emit_program(paths, profile, clearance)
    checks = verify_sweep(copper, stock, program, diameter)
    trimmed = False
    if not checks["passed"] and allow_pad_trim:
        paths = trimmed_contour_paths(copper, diameter)
        content, program = emit_program(paths, profile, clearance)
        checks = verify_sweep(copper, stock, program, diameter, allow_loss=True)
        trimmed = True
    additional = []
    if passes == 2 and checks["passed"]:
        first_swept = emitted_paths(program).buffer(diameter/2, quad_segs=32)
        additional = [path for path in outward_isolation_paths(copper, diameter)
                      if LineString(path).buffer(diameter/2, quad_segs=32)
                      .difference(first_swept).area > .0001]
        paths = paths + additional
        content, program = emit_program(paths, profile, clearance)
        checks = verify_sweep(copper, stock, program, diameter, allow_loss=trimmed)
        swept = emitted_paths(program).buffer(diameter/2, quad_segs=32)
        extra_loss = swept.intersection(copper.difference(first_swept))
        checks["wideningCopperLossMm2"] = extra_loss.area
        if extra_loss.area > .0001:
            point = extra_loss.representative_point()
            checks["findings"].append({
                "message": "Dodatkowy przejazd narusza projektowaną miedź.",
                "x": point.x, "y": point.y})
            checks["passed"] = False
    review = None
    removed = GeometryCollection()
    if allow_pad_trim:
        swept = emitted_paths(program).buffer(diameter/2, quad_segs=32)
        removed = copper.intersection(swept)
        if removed.area <= .0001:
            removed = GeometryCollection()
        changes = []
        for target in polygons(copper):
            loss = target.intersection(swept)
            if loss.area > .0001:
                point = loss.representative_point()
                changes.append({"x": point.x, "y": point.y,
                    "areaMm2": loss.area, "percent": loss.area/target.area*100})
        if checks["passed"] and changes:
            review = {"kind": "pad-trim/v1", "removedAreaMm2": removed.area,
                      "affectedIslands": changes, "requiresAcceptance": True}
            review["id"] = hashlib.sha256(json.dumps({
                "source": project, "profile": profile["fingerprint"],
                "program": content, "review": review}, sort_keys=True).encode()).hexdigest()
    preview = {"bounds": list(stock.bounds), "paths": paths,
               "copper": [[list(region.exterior.coords),
                            *[list(ring.coords) for ring in region.interiors]]
                           for region in polygons(copper)],
               "removedCopper": [[list(region.exterior.coords),
                                  *[list(ring.coords) for ring in region.interiors]]
                                 for region in polygons(removed)],
               "padTrimReviewId": review["id"] if review else None}
    report = {"engine": ENGINE, "transform": transform,
              "diameterMm": diameter, "depthMm": depth,
              "isolation": {"passes": passes, "overlapPercent": 50 if passes == 2 else 0,
                            "stepOverMm": diameter/2 if passes == 2 else 0,
                            "nominalWidthMm": band_width,
                            "widthIsNominal": True,
                            "direction": "outward",
                            "additionalContours": len(additional)},
              "clearanceMm": clearance, "conditions": conditions,
              "numerics": {"offsetMarginMm": MARGIN,
                           "voronoiUnionGridMm": NC_GRID,
                           "voronoiSitePerturbationMm": NC_GRID,
                           "simplificationMm": .004,
                           "gerberArcErrorMm": .001},
              "checks": checks, "boundsMm": program["bounds_mm"],
              "commands": len(program["lines"]),
              "padTrimReview": review,
              "operations": {"isolation": "ready" if checks["passed"]
                             else "blocked", "drilling": "not_prepared",
                             "outline": "not_prepared"}}
    return report, preview, content if checks["passed"] else None

# ---------------------------------------------------------------------------
# end of file
# ---------------------------------------------------------------------------
