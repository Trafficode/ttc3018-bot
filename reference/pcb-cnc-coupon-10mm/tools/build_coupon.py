# ---------------------------------------------------------------------------
# build_coupon.py
# 2026-10-12
# - Build and measure a 10 mm native KiCad isolation-milling coupon.
# ---------------------------------------------------------------------------
"""Use the existing coupon helpers and KiCad API; never operate hardware."""

import hashlib
import importlib.util
import json
import math
from pathlib import Path

import pcbnew


ROOT = Path(__file__).resolve().parent.parent
NAME = "cnc-coupon-10mm"
HELPERS = ROOT.parent / "pcb-cnc-coupon-40mm/tools/build_coupon.py"
SPEC = importlib.util.spec_from_file_location("coupon_helpers", HELPERS)
BUILD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BUILD)
# Only the new project receives files. The older coupon remains unchanged.
BUILD.ROOT = ROOT
BUILD.NAME = NAME
VALUES = (0.2, 0.5, 0.7)
ROWS = (1.7, 3.5, 5.5)


def verify(filename):
    """Measure requirements in the saved board rather than editor memory."""
    board = pcbnew.LoadBoard(str(filename))
    points = []
    for item in board.GetDrawings():
        if item.GetLayer() == pcbnew.Edge_Cuts:
            points.extend((item.GetStart(), item.GetEnd()))
    assert len(points) == 8
    xs = [point.x for point in points]
    ys = [point.y for point in points]
    size = [pcbnew.ToMM(max(xs) - min(xs)),
            pcbnew.ToMM(max(ys) - min(ys))]
    assert size == [10.0, 10.0]
    footprints = {item.GetReference(): item
                  for item in board.GetFootprints()}
    measurements = []
    for index, expected in enumerate(VALUES, 1):
        tracks = [item for item in board.GetTracks()
                  if item.GetNetname() == f"WIDTH_{expected:g}"]
        assert len(tracks) == 1
        width = pcbnew.ToMM(tracks[0].GetWidth())
        pads = sorted(footprints[f"G{index}"].Pads(),
                      key=lambda item: item.GetNumber())
        distance = abs(pads[0].GetPosition().y - pads[1].GetPosition().y)
        half_sizes = (pads[0].GetSize().y + pads[1].GetSize().y) // 2
        gap = pcbnew.ToMM(distance - half_sizes)
        assert abs(width - expected) < 0.000001
        assert abs(gap - expected) < 0.000001
        assert pads[0].GetNetCode() != pads[1].GetNetCode()
        measurements.append({"width_mm": width, "gap_mm": gap})
    pad = list(footprints["V1"].Pads())[0]
    assert pad.GetShape() == pcbnew.PAD_SHAPE_CHAMFERED_RECT
    assert pad.GetChamferPositions() == 15
    assert abs(pad.GetChamferRectRatio() - (1 - 1 / math.sqrt(2))) < 1e-6
    assert pcbnew.ToMM(pad.GetSize().x) == 2.0
    assert pcbnew.ToMM(pad.GetDrillSize().x) == 0.8
    assert board.GetDesignSettings().GetAuxOrigin() == BUILD.position(0, 10)
    report = {
        "result": "PASS", "kicad_version": pcbnew.Version(),
        "toolkit_revision": "b49f118ec6dc9237206e67b1a3710410133cecdf",
        "outline_mm": size, "samples": measurements,
        "via": {"across_flats_mm": 2, "drill_mm": 0.8,
                "minimum_copper_ring_mm": 0.6, "corners": 8},
        "origin": "lower-left outline corner, common export datum",
        "erc_parity_simulation": "N/A: passive board-only coupon",
        "physical_milling": "UNVERIFIED", "sha256": {},
    }
    for source in (filename, ROOT / (NAME + ".kicad_pro"), HELPERS,
                   Path(__file__).resolve()):
        report["sha256"][source.relative_to(ROOT.parent).as_posix()] = (
            hashlib.sha256(source.read_bytes()).hexdigest()
        )
    (ROOT / "validation/geometry.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, indent=2))


def main():
    """Create copper samples, octagonal drilled pad and closed outline."""
    (ROOT / "CncCoupon.pretty").mkdir(parents=True, exist_ok=True)
    (ROOT / "validation").mkdir(exist_ok=True)
    board = pcbnew.BOARD()
    board.SetCopperLayerCount(2)
    board.GetDesignSettings().SetBoardThickness(pcbnew.FromMM(1.6))
    corners = ((0, 0), (10, 0), (10, 10), (0, 10))
    for index, start in enumerate(corners):
        BUILD.line(board, start, corners[(index + 1) % 4], pcbnew.Edge_Cuts)
    for index, (value, y) in enumerate(zip(VALUES, ROWS), 1):
        width_net = BUILD.net(board, f"WIDTH_{value:g}")
        footprint = BUILD.custom(board, f"W{index}", f"Width_{value:g}mm")
        for number, x in ((1, -1.25), (2, 1.25)):
            BUILD.pad(footprint, number, x, 0, 0.8, 0.8, width_net)
        BUILD.finish_custom(board, footprint, 2.75, y)
        BUILD.track(board, (1.5, y), (4, y), value, width_net)
        footprint = BUILD.custom(board, f"G{index}", f"Gap_{value:g}mm")
        for number, sign in ((1, -1), (2, 1)):
            item_net = BUILD.net(board, f"GAP_{value:g}_{number}")
            BUILD.pad(footprint, number, 0, sign * (0.4 + value) / 2,
                      3, 0.4, item_net)
        BUILD.finish_custom(board, footprint, 7, y)
        # Screen/paper labels only; they are absent from milling copper exports.
        BUILD.text(board, f"{value:g}", 4.95, y, 0.4,
                   layer=pcbnew.Dwgs_User)
    footprint = BUILD.custom(board, "V1", "Octagon_2mm_Drill_0.8mm")
    pad = BUILD.pad(footprint, 1, 0, 0, 2, 2,
                    BUILD.net(board, "MANUAL_VIA"), drill=0.8)
    pad.SetShape(pcbnew.PAD_SHAPE_CHAMFERED_RECT)
    pad.SetChamferRectRatio(1 - 1 / math.sqrt(2))
    pad.SetChamferPositions(15)
    BUILD.finish_custom(board, footprint, 3, 8)
    BUILD.text(board, "OCT 2 / D0.8", 7, 8, 0.4,
               layer=pcbnew.Dwgs_User)
    BUILD.text(board, "W / GAP mm", 5, 0.5, 0.45,
               layer=pcbnew.Dwgs_User)
    board.GetDesignSettings().SetAuxOrigin(BUILD.position(0, 10))
    board.GetDesignSettings().SetGridOrigin(BUILD.position(0, 10))
    filename = ROOT / (NAME + ".kicad_pcb")
    pcbnew.SaveBoard(str(filename), board)
    BUILD.project_files()
    project_path = ROOT / (NAME + ".kicad_pro")
    project = json.loads(project_path.read_text(encoding="utf-8"))
    rules = project["board"]["design_settings"]["rules"]
    rules["min_copper_edge_clearance"] = 1.0
    project_path.write_text(json.dumps(project, indent=2) + "\n",
                            encoding="utf-8")
    (ROOT / "fp-lib-table").write_text(
        '(fp_lib_table\n (version 7)\n'
        ' (lib (name "CncCoupon")(type "KiCad")'
        '(uri "${KIPRJMOD}/CncCoupon.pretty")'
        '(options "")(descr "Machining samples"))\n)\n',
        encoding="utf-8",
    )
    verify(filename)


if __name__ == "__main__":
    main()

# ---------------------------------------------------------------------------
# end of file
# ---------------------------------------------------------------------------
