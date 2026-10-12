# ---------------------------------------------------------------------------
# plot_jobs.py
# 2026-10-12
# - Overlay verified G-code centreline paths on the native KiCad layer preview.
# ---------------------------------------------------------------------------
"""Render CAM evidence in the same datum as the unmirrored KiCad drawing."""

import json
from pathlib import Path

import pymupdf


ROOT = Path(__file__).resolve().parent.parent
MM_TO_PT = 72 / 25.4


def point(coordinates):
    """Convert lower-left machine XY to KiCad editor PDF coordinates."""
    x, y = coordinates
    return pymupdf.Point((100 + x) * MM_TO_PT, (110 - y) * MM_TO_PT)


def main():
    """Plot cut centre lines, then reopen and rasterize the saved PDF."""
    report = json.loads((ROOT / "validation/cam.json").read_text())
    segments = report["files"]["02-copper-mark-and-isolate.nc"]["segments"]
    document = pymupdf.open(ROOT / "validation/layout.pdf")
    page = document[0]
    shape = page.new_shape()
    for segment in segments:
        if segment["motion"] != 1 or segment["z"] >= 0:
            continue
        # Blue is the shallow border; red is the isolation tool centreline.
        colour = (0.1, 0.35, 0.9) if segment["z"] == -0.07 else (0.9, 0.1, 0.1)
        shape.draw_line(point(segment["from"]), point(segment["to"]))
        shape.finish(color=colour,
                     width=(0.137513 if segment["z"] == -0.07
                            else 0.126795) * MM_TO_PT,
                     stroke_opacity=0.6)
    shape.commit(overlay=True)
    destination = ROOT / "validation/toolpaths.pdf"
    document.save(destination)
    document.close()
    with pymupdf.open(destination) as saved:
        saved[0].get_pixmap(
            matrix=pymupdf.Matrix(20, 20),
            clip=pymupdf.Rect(282, 281, 314, 314),
        ).save(ROOT / "validation/toolpaths.png")
    print("Saved native-copper and G-code centreline overlay")


if __name__ == "__main__":
    main()

# ---------------------------------------------------------------------------
# end of file
# ---------------------------------------------------------------------------
