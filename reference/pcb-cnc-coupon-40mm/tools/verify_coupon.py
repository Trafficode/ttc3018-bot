# ---------------------------------------------------------------------------
# verify_coupon.py
# 2026-10-12
# - Measure saved KiCad coupon geometry and bind evidence to source hashes.
# ---------------------------------------------------------------------------
"""Verify the reopened board independently of the generator's placement code."""

import hashlib
import json
from pathlib import Path

import pcbnew


ROOT = Path(__file__).resolve().parent.parent
NAME = "cnc-coupon-40mm"
EXPECTED = [1.0, 0.8, 0.6, 0.5, 0.4, 0.3, 0.25, 0.2]


def require_close(actual, expected, description):
    """Reject dimension errors above one micrometre in the saved model."""
    if abs(actual - expected) > 0.001:
        raise AssertionError(f"{description}: {actual} != {expected} mm")


def main():
    """Measure layout, drill and datum requirements; never access hardware."""
    filename = ROOT / (NAME + ".kicad_pcb")
    board = pcbnew.LoadBoard(str(filename))
    edge_points = []
    for item in board.GetDrawings():
        if item.GetLayer() == pcbnew.Edge_Cuts:
            edge_points.extend((item.GetStart(), item.GetEnd()))
    if len(edge_points) != 8:
        raise AssertionError("Expected exactly four outline segments")
    edge_x = [point.x for point in edge_points]
    edge_y = [point.y for point in edge_points]
    size_x = pcbnew.ToMM(max(edge_x) - min(edge_x))
    size_y = pcbnew.ToMM(max(edge_y) - min(edge_y))
    require_close(size_x, 40, "Outline width")
    require_close(size_y, 40, "Outline height")
    footprints = {}
    for footprint in board.GetFootprints():
        footprints[footprint.GetReference()] = footprint
    rows = []
    for index, expected in enumerate(EXPECTED):
        matching_tracks = []
        for track in board.GetTracks():
            if track.GetNetname() == f"WIDTH_{expected:g}":
                matching_tracks.append(track)
        if len(matching_tracks) != 1:
            raise AssertionError("Missing or duplicate width sample")
        width = pcbnew.ToMM(matching_tracks[0].GetWidth())
        require_close(width, expected, "Track width")
        row = {"nominal_mm": expected, "track_width_mm": width}
        for orientation in ("H", "V"):
            footprint = footprints[f"G{index + 1}{orientation}"]
            pads = sorted(footprint.Pads(), key=lambda item: item.GetNumber())
            if pads[0].GetNetCode() == pads[1].GetNetCode():
                raise AssertionError("Clearance probes unexpectedly connected")
            if orientation == "H":
                distance = abs(
                    pads[0].GetPosition().y - pads[1].GetPosition().y
                )
                size_sum = pads[0].GetSize().y + pads[1].GetSize().y
            else:
                distance = abs(
                    pads[0].GetPosition().x - pads[1].GetPosition().x
                )
                size_sum = pads[0].GetSize().x + pads[1].GetSize().x
            gap = pcbnew.ToMM(int(distance - size_sum / 2))
            require_close(gap, expected, "Copper edge gap " + orientation)
            row["gap_" + orientation + "_mm"] = gap
        rows.append(row)
    holes = []
    for index in range(8):
        footprint = footprints[f"D{index + 1}"]
        item = list(footprint.Pads())[0]
        drill = pcbnew.ToMM(item.GetDrillSize().x)
        require_close(drill, (0.6, 0.8, 1.0, 1.2)[index % 4], "Drill")
        ring = (pcbnew.ToMM(item.GetSize().x) - drill) / 2
        holes.append({"ref": footprint.GetReference(), "drill_mm": drill,
                      "ring_mm": round(ring, 3)})
    for first, second in (("F1", "F2"), ("F3", "F4")):
        distance = footprints[second].GetPosition().x
        distance -= footprints[first].GetPosition().x
        require_close(pcbnew.ToMM(distance), 36, "Horizontal fiducial span")
    for first, second in (("F1", "F3"), ("F2", "F4")):
        distance = footprints[second].GetPosition().y
        distance -= footprints[first].GetPosition().y
        require_close(pcbnew.ToMM(distance), 36, "Vertical fiducial span")
    origin = board.GetDesignSettings().GetAuxOrigin()
    if origin != footprints["O1"].GetPosition():
        raise AssertionError("Datum differs from auxiliary origin")
    rules = board.GetDesignSettings()
    require_close(pcbnew.ToMM(rules.m_MinClearance), 0.2, "DRC clearance")
    require_close(pcbnew.ToMM(rules.m_TrackMinWidth), 0.2, "DRC track width")
    report = {
        "result": "PASS", "kicad_version": pcbnew.Version(),
        "dimension_tolerance_mm": 0.001,
        "outline_mm": [size_x, size_y],
        "rows": rows, "drill_samples": holes,
        "fiducial_square_mm": 36,
        "datum_editor_mm": [pcbnew.ToMM(origin.x), pcbnew.ToMM(origin.y)],
        "erc_and_schematic_parity": "N/A: passive board-only test coupon",
        "bench_capability": "UNVERIFIED: physical milling not performed",
        "sha256": {},
    }
    for source in sorted(ROOT.glob("*.kicad_*")):
        if source.suffix in (".kicad_pcb", ".kicad_pro"):
            report["sha256"][source.name] = hashlib.sha256(
                source.read_bytes()
            ).hexdigest()
    destination = ROOT / "validation/geometry.json"
    destination.write_text(json.dumps(report, indent=2) + "\n",
                           encoding="utf-8")
    print("PASS: outline datum, eight widths, sixteen gaps and eight drills")


if __name__ == "__main__":
    main()

# ---------------------------------------------------------------------------
# end of file
# ---------------------------------------------------------------------------
