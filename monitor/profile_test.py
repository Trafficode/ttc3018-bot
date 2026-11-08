# ---------------------------------------------------------------------------
# profile_test.py
# 2026-10-24
# - Fixed-profile isolation test geometry with explicit material and map bounds.
# ---------------------------------------------------------------------------
"""The preview and G-code share the exact same paths; no machine access."""

import math

from monitor.calibration import settings, tool_diameter
from monitor.jobs import parse_program


def configuration(store, payload=None):
    """Read every cutting parameter from the immutable selected profile."""
    profile = store.active
    if "depth" not in profile or "conditions" not in profile:
        raise ValueError("Ten profil nie ma stałej głębokości. "
                         "Ustaw ją w Ustawieniach i zapisz zmiany.")
    config = settings({**profile["conditions"], "depth": profile["depth"],
                       "width": 1})
    expected = {"profile_id": profile["id"],
                "profile_fingerprint": profile["fingerprint"]}
    if payload is not None:
        if any(payload.get(key) != value for key, value in expected.items()):
            raise ValueError("Profil testu zmienił się; odśwież podgląd.")
        if any(key in payload and payload[key] != value
               for key, value in config.items()):
            raise ValueError("Test używa wyłącznie parametrów profilu.")
    return store.resolve(config, expected)


def layout(config):
    """Three 10 mm copper strips and two octagons, with outward offsets.

    Octagon diameter means opposite vertices. Offsetting each flat edge by
    the tool radius therefore increases circumradius by r/cos(pi/8).
    """
    diameter = tool_diameter(config, config["depth"])
    radius = diameter / 2
    gap = max(.5, 2 * diameter + .2)
    shapes = []
    cursor = 0
    for width in (.3, .5, 1):
        x, y = 0, cursor
        copper = [[x, y], [x + 10, y], [x + 10, y + width], [x, y + width]]
        path = [[x - radius, y - radius],
                [x + 10 + radius, y - radius],
                [x + 10 + radius, y + width + radius],
                [x - radius, y + width + radius]]
        shapes.append({"kind": "strip", "width": width, "length": 10,
                       "copper": copper, "path": path})
        cursor += width + gap
    for size, cx in ((1, 1), (2, 2.5 + gap)):
        centre = [cx, cursor + 1]
        copper, path = [], []
        for index in range(8):
            angle = index * math.pi / 4
            for points, distance in (
                (copper, size / 2),
                (path, size / 2 + radius / math.cos(math.pi / 8)),
            ):
                points.append([centre[0] + distance * math.cos(angle),
                               centre[1] + distance * math.sin(angle)])
        shapes.append({"kind": "octagon", "diameter": size,
                       "copper": copper, "path": path})
    # Bound the full cutter sweep, not just copper or tool centre lines.
    # Translate the pattern so each outer sweep edge has exactly 1 mm margin.
    path_points = [point for shape in shapes for point in shape["path"]]
    low_x = min(point[0] for point in path_points) - radius
    high_x = max(point[0] for point in path_points) + radius
    low_y = min(point[1] for point in path_points) - radius
    high_y = max(point[1] for point in path_points) + radius
    border = 1.0
    width = high_x - low_x + 2 * border
    height = high_y - low_y + 2 * border
    for shape in shapes:
        for key in ("copper", "path"):
            shape[key] = [[x - low_x + border, y - low_y + border]
                          for x, y in shape[key]]
    if width > 20 or height > 20:
        raise ValueError("Rowek profilu jest za szeroki dla małego testu.")
    return {"width": width, "height": height, "diameter": diameter,
            "margin_mm": border,
            "shapes": shapes,
            "settings": settings(config)}


def preview(store):
    """Expose offline geometry even while CNC is disconnected."""
    try:
        return layout(configuration(store))
    except ValueError as error:
        return {"error": str(error)}


def program(origin, config):
    """Cut closed isolation contours; do not remove unused copper areas."""
    plan = layout(config)
    ox, oy = origin
    commands = ["G21 G90 G94 G54", "M5", "G0 Z2"]
    for index, shape in enumerate(plan["shapes"]):
        points = shape["path"]
        x, y = points[0]
        commands.append(f"G0 X{ox+x:.4f} Y{oy+y:.4f}")
        if index == 0:
            commands.extend([f"M3 S{config['power']:g}", "G4 P2"])
        commands.append(f"G1 Z{-config['depth']:.4f} "
                        f"F{config['plunge']:g}")
        for x, y in points[1:] + points[:1]:
            commands.append(f"G1 X{ox+x:.4f} Y{oy+y:.4f} "
                            f"F{config['feed']:g}")
        commands.append("G0 Z2")
    commands.extend(["M5", "M30"])
    result = parse_program("profile-test.nc", "\n".join(commands))
    result["tool_geometry"] = {
        "diameter_mm": plan["diameter"], "depth_mm": config["depth"],
        "strip_width_mm": 1, "centreline_spacing_mm": 1 + plan["diameter"],
        "profile_id": config.get("_calibration", {}).get("id", "default"),
        "correction": config.get("_calibration", {}).get("model"),
    }
    return result

# ---------------------------------------------------------------------------
# end of file
# ---------------------------------------------------------------------------
