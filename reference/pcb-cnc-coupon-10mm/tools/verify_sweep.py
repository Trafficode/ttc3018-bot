# ---------------------------------------------------------------------------
# verify_sweep.py
# 2026-10-12
# - Check nominal swept cutter area and render the resulting copper.
# ---------------------------------------------------------------------------
"""Simulate planar copper removal; mechanical accuracy remains unverified."""

import json
from pathlib import Path

from PIL import Image, ImageDraw
from shapely.geometry import LineString, Polygon, box
from shapely.ops import unary_union


ROOT = Path(__file__).resolve().parent.parent


def main():
    """Check separate test nets and absence of isolated waste copper islands."""
    report = json.loads((ROOT / "validation/cam.json").read_text())
    segments = report["files"]["02-copper-mark-and-isolate.nc"]["segments"]
    paths = []
    for segment in segments:
        if segment["motion"] != 1 or segment["z"] >= 0:
            continue
        if segment["from"] == segment["to"]:
            continue
        diameter = 0.137513 if segment["z"] == -0.07 else 0.126795
        paths.append(LineString([segment["from"], segment["to"]]).buffer(
            diameter / 2, quad_segs=32
        ))
    remaining = box(0, 0, 10, 10).difference(unary_union(paths))
    components = list(remaining.geoms)
    # These are the already measured, unchanged native coupon requirements.
    expected = []
    for width, y in ((0.2, 8.3), (0.5, 6.5), (0.7, 4.5)):
        pads = [box(x - 0.4, y - 0.4, x + 0.4, y + 0.4)
                for x in (1.5, 4)]
        track = LineString([(1.5, y), (4, y)]).buffer(width / 2)
        expected.append(unary_union(pads + [track]))
        for sign in (-1, 1):
            cy = y + sign * (0.4 + width) / 2
            expected.append(box(5.5, cy - 0.2, 8.5, cy + 0.2))
    c = 2 * (1 - 1 / (2 ** 0.5))
    expected.append(Polygon([(2 + c, 1), (4 - c, 1), (4, 1 + c),
                             (4, 3 - c), (4 - c, 3), (2 + c, 3),
                             (2, 3 - c), (2, 1 + c)]))
    assigned = []
    losses = []
    for feature in expected:
        index = max(range(len(components)),
                    key=lambda i: feature.intersection(components[i]).area)
        overlap = feature.intersection(components[index]).area
        if overlap < feature.area * 0.98:
            raise ValueError("More than 2 percent nominal test copper removed")
        assigned.append(index)
        losses.append(feature.area - overlap)
    if len(set(assigned)) != 10:
        raise ValueError("Test nets joined or missing after nominal milling")
    waste = [item for i, item in enumerate(components) if i not in assigned]
    if len(waste) != 1:
        print("Waste components:", [(item.area, item.bounds) for item in waste])
        raise ValueError("Isolated unwanted copper remnants remain")
    evidence = {
        "result": "PASS", "model": "nominal flat copper, zero runout",
        "desired_copper_components": 10,
        "connected_background_components": len(waste),
        "isolated_waste_islands": 0,
        "maximum_feature_area_loss_mm2": max(losses),
        "geometry_tolerance_note": "CAM tolerance 0.002 mm; rounded corners",
        "physical_acceptance": "UNVERIFIED",
    }
    (ROOT / "validation/sweep.json").write_text(
        json.dumps(evidence, indent=2) + "\n", encoding="utf-8"
    )
    image = Image.new("RGB", (880, 900), "white")
    draw = ImageDraw.Draw(image)

    def pixels(ring):
        return [(60 + x * 75, 810 - y * 75) for x, y in ring.coords]

    for component in sorted(components, key=lambda item: item.area,
                            reverse=True):
        draw.polygon(pixels(component.exterior), fill="#be7d43")
        for hole in component.interiors:
            draw.polygon(pixels(hole), fill="white")
    draw.text((60, 15), "10 x 10 mm | nominal remaining copper", fill="black")
    draw.text((60, 840), "White = removed copper. No drilled hole.",
              fill="black")
    image.save(ROOT / "validation/remaining-copper.png")
    print(json.dumps(evidence, indent=2))


if __name__ == "__main__":
    main()

# ---------------------------------------------------------------------------
# end of file
# ---------------------------------------------------------------------------
