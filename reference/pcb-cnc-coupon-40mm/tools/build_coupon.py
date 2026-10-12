# ---------------------------------------------------------------------------
# build_coupon.py
# 2026-10-12
# - Build a native KiCad 40 mm CNC process coupon and portable local library.
# ---------------------------------------------------------------------------
"""Generate a passive machining coupon with KiCad's installed pcbnew API."""

import json
from pathlib import Path

import pcbnew


ROOT = Path(__file__).resolve().parent.parent
NAME = "cnc-coupon-40mm"
KICAD_SHARE = Path(pcbnew.__file__).resolve().parents[3] / "share/kicad"
VALUES = [1.0, 0.8, 0.6, 0.5, 0.4, 0.3, 0.25, 0.2]
ORIGIN = (100.0, 100.0)


def vector(x, y):
    """Convert millimetres to KiCad integer coordinates."""
    return pcbnew.VECTOR2I(pcbnew.FromMM(x), pcbnew.FromMM(y))


def position(x, y):
    """Convert board-local coordinates to editor coordinates."""
    return vector(ORIGIN[0] + x, ORIGIN[1] + y)


def layers(*names):
    """Create an explicit pad layer set."""
    result = pcbnew.LSET()
    for name in names:
        result.AddLayer(name)
    return result


def net(board, name):
    """Add a net whose continuity or isolation can be measured."""
    result = pcbnew.NETINFO_ITEM(board, name)
    board.Add(result)
    return result


def line(board, start, end, layer, width=0.1):
    """Add a native drawing segment using board-local millimetres."""
    shape = pcbnew.PCB_SHAPE(board)
    shape.SetShape(pcbnew.SHAPE_T_SEGMENT)
    shape.SetStart(position(*start))
    shape.SetEnd(position(*end))
    shape.SetLayer(layer)
    shape.SetWidth(pcbnew.FromMM(width))
    board.Add(shape)


def text(board, content, x, y, size=0.75, layer=pcbnew.F_SilkS):
    """Add non-copper identification text; milling does not make silkscreen."""
    item = pcbnew.PCB_TEXT(board)
    item.SetText(content)
    item.SetPosition(position(x, y))
    item.SetTextSize(vector(size, size))
    item.SetTextThickness(pcbnew.FromMM(0.12))
    item.SetLayer(layer)
    board.Add(item)


def custom(board, reference, name):
    """Start a locally defined, documented diagnostic footprint."""
    footprint = pcbnew.FOOTPRINT(board)
    footprint.SetFPIDAsString("CncCoupon:" + name)
    footprint.SetReference(reference)
    footprint.SetValue(name)
    footprint.Reference().SetVisible(False)
    footprint.Value().SetVisible(False)
    footprint.SetAttributes(
        pcbnew.FP_EXCLUDE_FROM_BOM | pcbnew.FP_EXCLUDE_FROM_POS_FILES
    )
    return footprint


def pad(footprint, number, x, y, sx, sy, net_item, drill=None):
    """Create exposed copper pads, optionally with through-drill geometry."""
    item = pcbnew.PAD(footprint)
    item.SetNumber(str(number))
    item.SetPosition(vector(x, y))
    item.SetSize(vector(sx, sy))
    item.SetNet(net_item)
    if drill is None:
        item.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
        shape = pcbnew.PAD_SHAPE_RECT
        item.SetLayerSet(layers(pcbnew.F_Cu, pcbnew.F_Mask))
    else:
        item.SetAttribute(pcbnew.PAD_ATTRIB_PTH)
        shape = pcbnew.PAD_SHAPE_CIRCLE
        item.SetDrillSize(vector(drill, drill))
        through_layers = pcbnew.LSET.AllCuMask()
        through_layers.AddLayer(pcbnew.F_Mask)
        through_layers.AddLayer(pcbnew.B_Mask)
        item.SetLayerSet(through_layers)
    item.SetShape(shape)
    footprint.Add(item)
    return item


def finish_custom(board, footprint, x, y):
    """Save an editable project-library footprint, then place its instance."""
    # Courtyard follows the actual copper extent, including experimental bars.
    pads = list(footprint.Pads())
    min_x = min(item.GetPosition().x - item.GetSize().x / 2 for item in pads)
    max_x = max(item.GetPosition().x + item.GetSize().x / 2 for item in pads)
    min_y = min(item.GetPosition().y - item.GetSize().y / 2 for item in pads)
    max_y = max(item.GetPosition().y + item.GetSize().y / 2 for item in pads)
    margin = pcbnew.FromMM(0.2)
    corners = [
        (min_x - margin, min_y - margin),
        (max_x + margin, min_y - margin),
        (max_x + margin, max_y + margin),
        (min_x - margin, max_y + margin),
    ]
    for index, start in enumerate(corners):
        end = corners[(index + 1) % 4]
        shape = pcbnew.PCB_SHAPE(footprint)
        shape.SetShape(pcbnew.SHAPE_T_SEGMENT)
        shape.SetStart(pcbnew.VECTOR2I(int(start[0]), int(start[1])))
        shape.SetEnd(pcbnew.VECTOR2I(int(end[0]), int(end[1])))
        shape.SetLayer(pcbnew.F_CrtYd)
        shape.SetWidth(pcbnew.FromMM(0.05))
        footprint.Add(shape)
    plugin = pcbnew.PCB_IO_MGR.FindPlugin(pcbnew.PCB_IO_MGR.KICAD_SEXP)
    plugin.FootprintSave(str(ROOT / "CncCoupon.pretty"), footprint)
    board.Add(footprint)
    footprint.SetPosition(position(x, y))


def track(board, start, end, width, net_item):
    """Connect the two probe pads of a width test."""
    item = pcbnew.PCB_TRACK(board)
    item.SetStart(position(*start))
    item.SetEnd(position(*end))
    item.SetWidth(pcbnew.FromMM(width))
    item.SetLayer(pcbnew.F_Cu)
    item.SetNet(net_item)
    board.Add(item)


def width_tests(board):
    """Add eight independent horizontal traces with accessible end pads."""
    for index, width in enumerate(VALUES):
        y = 6.5 + 2.8 * index
        reference = f"W{index + 1}"
        item_net = net(board, f"WIDTH_{width:g}")
        footprint = custom(board, reference, f"Width_{width:g}mm")
        left = pad(footprint, 1, -4.5, 0, 1.3, 1.3, item_net)
        right = pad(footprint, 2, 4.5, 0, 1.3, 1.3, item_net)
        left.SetShape(pcbnew.PAD_SHAPE_CIRCLE)
        right.SetShape(pcbnew.PAD_SHAPE_CIRCLE)
        finish_custom(board, footprint, 9.5, y)
        track(board, (5, y), (14, y), width, item_net)
        text(board, f"{width:g}", 2.2, y)
        if width < 0.4:
            text(board, "EXP", 16.6, y, 0.6)


def gap_tests(board):
    """Test exact copper clearances in both horizontal and vertical pairs."""
    for index, gap in enumerate(VALUES):
        y = 6.5 + 2.8 * index
        for direction in ("H", "V"):
            footprint = custom(
                board, f"G{index + 1}{direction}",
                f"Gap_{gap:g}mm_{direction}",
            )
            distance = (0.6 + gap) / 2
            for number, sign in ((1, -1), (2, 1)):
                item_net = net(board, f"GAP_{gap:g}_{direction}_{number}")
                if direction == "H":
                    pad(footprint, number, 0, sign * distance,
                        7.0, 0.6, item_net)
                else:
                    pad(footprint, number, sign * distance, 0,
                        0.6, 2.0, item_net)
            x = 26 if direction == "H" else 35
            finish_custom(board, footprint, x, y)
        text(board, f"{gap:g}", 20.4, y)


def component(board, reference, library, name, value, x, y, angle=0):
    """Load a KiCad footprint with independently isolated unused pads."""
    footprint = pcbnew.FootprintLoad(
        str(KICAD_SHARE / "footprints" / (library + ".pretty")), name
    )
    if footprint is None:
        raise RuntimeError("Missing installed footprint: " + name)
    footprint.SetFPIDAsString(library + ":" + name)
    footprint.SetReference(reference)
    footprint.SetValue(value)
    footprint.Reference().SetVisible(False)
    footprint.Value().SetVisible(False)
    for item in footprint.Pads():
        item.SetNet(net(board, reference + "_" + item.GetNumber()))
    board.Add(footprint)
    footprint.SetPosition(position(x, y))
    footprint.SetOrientationDegrees(angle)


def solder_and_drill_tests(board):
    """Add standard hand-soldering footprints and two rows of drill samples."""
    for reference, name, value, x in (
        ("R1", "R_0603_1608Metric", "0603", 4.5),
        ("R2", "R_0805_2012Metric", "0805", 10.5),
        ("R3", "R_1206_3216Metric", "1206", 17),
    ):
        component(board, reference, "Resistor_SMD", name, value, x, 30)
        text(board, value, x, 28.3, 0.65)
    component(board, "U1", "Package_SO", "SOIC-8_3.9x4.9mm_P1.27mm",
              "SOIC-8", 6.7, 35.5)
    text(board, "SOIC-8", 6.7, 32.2, 0.65)
    component(board, "J1", "Connector_PinHeader_2.54mm",
              "PinHeader_1x02_P2.54mm_Vertical", "2.54mm", 18, 35, 90)
    text(board, "2.54", 16.7, 33, 0.65)
    text(board, "DRILL", 31, 28.3, 0.65)
    for index, diameter in enumerate((0.6, 0.8, 1.0, 1.2)):
        x = 25 + 4 * index
        for row, y in enumerate((30.5, 35.5)):
            ring = 0.6 if row == 0 else (0.25, 0.35, 0.45, 0.6)[index]
            name = f"Drill_{diameter:g}mm_Ring_{ring:g}mm"
            footprint = custom(board, f"D{row * 4 + index + 1}", name)
            size = diameter + 2 * ring
            pad(footprint, 1, 0, 0, size, size,
                net(board, name + f"_{row}"), drill=diameter)
            finish_custom(board, footprint, x, y)
            text(board, f"{diameter:g}", x, y + 1.7, 0.6)


def datum_and_fiducials(board):
    """Add a visible datum at (5, 5) and a 36 mm measurement square."""
    for reference, x, y in (
        ("F1", 2, 2), ("F2", 38, 2),
        ("F3", 2, 38), ("F4", 38, 38), ("O1", 5, 5),
    ):
        footprint = custom(board, reference, "Fiducial_0.6mm")
        item = pad(footprint, 1, 0, 0, 0.6, 0.6, net(board, reference))
        item.SetShape(pcbnew.PAD_SHAPE_CIRCLE)
        finish_custom(board, footprint, x, y)
    # The datum is a visual reference; CAM must intentionally use this origin.
    text(board, "XY0", 2.6, 4.5, 0.6)
    board.GetDesignSettings().SetAuxOrigin(position(5, 5))
    board.GetDesignSettings().SetGridOrigin(position(5, 5))


def project_files():
    """Use KiCad's native project template and explicit experimental limits."""
    template = KICAD_SHARE / "template/kicad.kicad_pro"
    project = json.loads(template.read_text(encoding="utf-8"))
    project["meta"]["filename"] = NAME + ".kicad_pro"
    rules = project["board"]["design_settings"]["rules"]
    rules.update({
        "min_clearance": 0.2, "min_track_width": 0.2,
        "min_through_hole_diameter": 0.6,
        "min_copper_edge_clearance": 1.5,
        "min_hole_clearance": 0.2, "min_hole_to_hole": 0.5,
        "min_text_height": 0.6, "min_text_thickness": 0.1,
    })
    project_path = ROOT / (NAME + ".kicad_pro")
    project_path.write_text(json.dumps(project, indent=2) + "\n",
                            encoding="utf-8")
    entries = [
        '(lib (name "CncCoupon")(type "KiCad")'
        '(uri "${KIPRJMOD}/CncCoupon.pretty")(options "")(descr ""))',
    ]
    for library in (
        "Resistor_SMD", "Package_SO", "Connector_PinHeader_2.54mm",
    ):
        entries.append(
            f'(lib (name "{library}")(type "KiCad")'
            f'(uri "${{KICAD10_FOOTPRINT_DIR}}/{library}.pretty")'
            '(options "")(descr ""))'
        )
    (ROOT / "fp-lib-table").write_text(
        '(fp_lib_table\n  (version 7)\n  '
        + "\n  ".join(entries) + '\n)\n', encoding="utf-8"
    )


def main():
    """Build the native project; do not create or execute any machine job."""
    ROOT.mkdir(parents=True, exist_ok=True)
    (ROOT / "CncCoupon.pretty").mkdir(exist_ok=True)
    board = pcbnew.BOARD()
    board.SetCopperLayerCount(2)
    board.GetDesignSettings().SetBoardThickness(pcbnew.FromMM(1.6))
    for start, end in (
        ((0, 0), (40, 0)), ((40, 0), (40, 40)),
        ((40, 40), (0, 40)), ((0, 40), (0, 0)),
    ):
        line(board, start, end, pcbnew.Edge_Cuts)
    text(board, "CNC TEST 40 / A", 21, 1.4, 0.9)
    text(board, "WIDTH mm", 10, 4.1)
    text(board, "GAP mm   H / V", 29, 4.1)
    line(board, (18, 5), (18, 27), pcbnew.Dwgs_User)
    line(board, (1.5, 27.2), (38.5, 27.2), pcbnew.Dwgs_User)
    width_tests(board)
    gap_tests(board)
    solder_and_drill_tests(board)
    datum_and_fiducials(board)
    filename = ROOT / (NAME + ".kicad_pcb")
    pcbnew.SaveBoard(str(filename), board)
    # SaveBoard also saves default project settings. Apply our explicit limits
    # afterwards so a first-generation project cannot silently lose them.
    project_files()
    reopened = pcbnew.LoadBoard(str(filename))
    # The rendered bounding box includes the Edge.Cuts stroke thickness.
    # Validate actual cut-line endpoints instead of subtracting a guessed stroke.
    endpoints = []
    for item in reopened.GetDrawings():
        if item.GetLayer() == pcbnew.Edge_Cuts:
            endpoints.extend((item.GetStart(), item.GetEnd()))
    xs = [pcbnew.ToMM(point.x) for point in endpoints]
    ys = [pcbnew.ToMM(point.y) for point in endpoints]
    actual = [max(xs) - min(xs), max(ys) - min(ys)]
    if actual != [40.0, 40.0]:
        raise RuntimeError(f"Unexpected outline dimensions: {actual}")
    print(json.dumps({
        "kicad": pcbnew.Version(), "outline_mm": actual,
        "footprints": len(list(reopened.GetFootprints())),
        "tracks": len(list(reopened.GetTracks())),
        "datum_board_mm": [5, 5],
    }, indent=2))


if __name__ == "__main__":
    main()

# ---------------------------------------------------------------------------
# end of file
# ---------------------------------------------------------------------------
