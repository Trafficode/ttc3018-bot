# ---------------------------------------------------------------------------
# profile_test.py
# 2026-10-24
# - Fixed-profile isolation test geometry with explicit material and map bounds.
# ---------------------------------------------------------------------------
"""The preview and G-code share the exact same paths; no machine access."""

import math

from monitor.calibration import settings, tool_diameter
from monitor.jobs import parse_program


OVERLAPS = (25, 50, 75)
STRIP_WIDTHS = (.3, .5)
FIELD_WIDTH = FIELD_HEIGHT = 5
STRIP_LENGTH = 1.45
MIN_STRIP_LENGTH = .8
EDGE_MARGIN = .4
MIN_SWEEP_GAP = .15
CORNER_ZONE_MM = .5


def configuration(store, payload=None):
    """Read every cutting parameter from the immutable selected profile."""
    profile = store.active
    if "depth" not in profile or "conditions" not in profile:
        raise ValueError("Ten profil nie ma stałej głębokości. "
                         "Ustaw ją w Ustawieniach i zapisz zmiany.")
    config = settings({**profile["conditions"], "depth": profile["depth"],
                       "width": STRIP_WIDTHS[-1]})
    config["corner_feed"] = profile.get("corner_feed")
    expected = {"profile_id": profile["id"],
                "profile_fingerprint": profile["fingerprint"]}
    if payload is not None:
        if any(payload.get(key) != value for key, value in expected.items()):
            raise ValueError("Profil testu zmienił się; odśwież podgląd.")
        if any(key in payload and payload[key] != value
               for key, value in config.items()):
            raise ValueError("Test używa wyłącznie parametrów profilu.")
    passes = (payload or {}).get("passes", 1)
    overlap = (payload or {}).get("overlap_percent", 50 if passes == 2 else 0)
    if type(passes) is not int or passes not in (1, 2) or (
        type(overlap) is not int or overlap not in (OVERLAPS if passes == 2 else (0,))
    ):
        raise ValueError("Wybierz obsługiwaną liczbę przejazdów i zakładkę.")
    return {**store.resolve(config, expected, allow_draft=True),
            "_profile_id": profile["id"], "passes": passes, "overlap_percent": overlap}


def layout(config):
    """Place two horizontal strips above two vertical strips in 5 × 5 mm."""
    diameter = tool_diameter(config, config["depth"])
    radius = diameter / 2
    passes = config.get("passes", 1)
    overlap = config.get("overlap_percent", 0)
    step = diameter * (1 - overlap / 100) if passes == 2 else 0
    total = diameter + step
    cell = (FIELD_WIDTH - 2 * EDGE_MARGIN - MIN_SWEEP_GAP) / 2
    length = min(STRIP_LENGTH, cell - 2 * total)
    if length < MIN_STRIP_LENGTH:
        raise ValueError("Rowki nie mieszczą się w polu 5 × 5 mm z wymaganym odstępem. "
                         "Wybierz jeden przejazd, większą zakładkę lub węższy rowek.")
    offsets = [radius + lane * step for lane in range(passes)]
    shapes = []
    near = EDGE_MARGIN + cell / 2
    for orientation, cy in (("horizontal", FIELD_HEIGHT - near), ("vertical", near)):
        for width, cx in zip(STRIP_WIDTHS, (near, FIELD_WIDTH - near)):
            dx, dy = (length, width) if orientation == "horizontal" else (width, length)
            x, y = cx - dx / 2, cy - dy / 2
            copper = [[x, y], [x + dx, y], [x + dx, y + dy], [x, y + dy]]
            paths = [[[x - offset, y - offset],
                      [x + dx + offset, y - offset],
                      [x + dx + offset, y + dy + offset],
                      [x - offset, y + dy + offset]]
                     for offset in offsets]
            shapes.append({"kind": "strip", "orientation": orientation,
                           "width": width, "length": length, "copper": copper,
                           "paths": paths, "path": paths[0]})
    return {"width": FIELD_WIDTH, "height": FIELD_HEIGHT, "diameter": diameter,
            "margin_mm": EDGE_MARGIN, "passes": passes, "overlap_percent": overlap,
            "step_mm": step, "total_mm": total, "strip_gap_mm": cell + MIN_SWEEP_GAP - length,
            "diameter_source": "calibrated" if config.get("_calibration") else "nominal",
            "shapes": shapes,
            "settings": {**settings(config), "corner_feed": config.get("corner_feed")},
            "corner_zone_mm": CORNER_ZONE_MM}


def preview(store):
    """Expose exact selectable geometry even while CNC is disconnected."""
    try:
        base = configuration(store)
        result = layout(base)
        result["profile_fingerprint"] = store.active["fingerprint"]
        result["variants"] = {}
        for overlap in OVERLAPS:
            try:
                result["variants"][str(overlap)] = layout(
                    {**base, "passes": 2, "overlap_percent": overlap})
            except ValueError as error:
                result["variants"][str(overlap)] = {"error": str(error)}
        return result
    except ValueError as error:
        return {"error": str(error)}


def contour_moves(points, feed, corner_feed):
    """Split the straight edges between turns of a closed coupon polygon."""
    targets = points[1:] + points[:1]
    if corner_feed is None or corner_feed == feed:
        yield from ((x, y, feed) for x, y in targets)
        return
    for start, end in zip(points, targets):
        x, y = start
        dx, dy = end[0] - x, end[1] - y
        length = math.hypot(dx, dy)
        # Avoid a redundant straight move below the G-code coordinate resolution.
        if length > 2 * CORNER_ZONE_MM + .0001:
            fraction = CORNER_ZONE_MM / length
            yield x + dx * fraction, y + dy * fraction, corner_feed
            yield end[0] - dx * fraction, end[1] - dy * fraction, feed
        yield end[0], end[1], corner_feed


def program(origin, config):
    """Cut closed isolation contours; do not remove unused copper areas."""
    plan = layout(config)
    ox, oy = origin
    commands = ["G21 G90 G94 G54", "M5", "G0 Z2"]
    for lane in range(plan["passes"]):
        for index, shape in enumerate(plan["shapes"]):
            points = shape["paths"][lane]
            x, y = points[0]
            commands.append(f"G0 X{ox+x:.4f} Y{oy+y:.4f}")
            if lane == index == 0:
                commands.extend([f"M3 S{config['power']:g}", "G4 P2"])
            commands.append(f"G1 Z{-config['depth']:.4f} "
                            f"F{config['plunge']:g}")
            for x, y, feed in contour_moves(points, config["feed"], config.get("corner_feed")):
                commands.append(f"G1 X{ox+x:.4f} Y{oy+y:.4f} "
                                f"F{feed:g}")
            commands.append("G0 Z2")
    commands.extend(["M5", "M30"])
    result = parse_program("profile-test.nc", "\n".join(commands))
    result["tool_geometry"] = {
        "diameter_mm": plan["diameter"], "depth_mm": config["depth"],
        "strip_width_mm": STRIP_WIDTHS[-1],
        "centreline_spacing_mm": STRIP_WIDTHS[-1] + plan["diameter"],
        "strip_widths": list(STRIP_WIDTHS),
        "strips": [{key: shape[key] for key in ("orientation", "width", "length")}
                   for shape in plan["shapes"]],
        "strip_lengths_mm": [shape["length"] for shape in plan["shapes"]],
        "strip_gap_mm": plan["strip_gap_mm"],
        "passes": plan["passes"], "overlap_percent": plan["overlap_percent"],
        "step_mm": plan["step_mm"],
        "profile_id": config.get("_profile_id", config.get("_calibration", {}).get("id", "default")),
        "correction": config.get("_calibration", {}).get("model"),
    }
    if config.get("corner_feed") is not None:
        result["tool_geometry"]["corner_feed_mm_min"] = config["corner_feed"]
        result["tool_geometry"]["corner_zone_mm"] = plan["corner_zone_mm"]
    return result

# ---------------------------------------------------------------------------
# end of file
# ---------------------------------------------------------------------------
