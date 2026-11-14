# ---------------------------------------------------------------------------
# build_coupon.py
# 2026-10-19
# - Build a compact KiCad coupon and a retained-copper isolation preview.
# ---------------------------------------------------------------------------
"""Use the installed KiCad API; create no machine commands or hardware work."""

import hashlib
import json
from pathlib import Path

import pcbnew
from PIL import Image, ImageDraw, ImageFilter, ImageFont


ROOT = Path(__file__).resolve().parent.parent
NAME = "cnc-coupon-20mm"
SHARE = Path(pcbnew.__file__).resolve().parents[3] / "share/kicad"
WIDTH = 12
HEIGHT = 11
TRACK_LENGTH = 3.5
COMPONENTS = [("SOT-23", 2.7), ("0805", 6.5), ("0603", 9.75)]
SAMPLES = [(0.5, 0.5, 1.5, 5.3), (0.5, 0.7, 7, 5.3),
           (0.7, 0.5, 1.5, 8), (0.7, 0.7, 7, 8)]


def vector(x, y):
    """Convert millimetres to editor units."""
    return pcbnew.VECTOR2I(pcbnew.FromMM(x), pcbnew.FromMM(y))


def position(x, y):
    """Keep the coupon away from the page origin."""
    return vector(100 + x, 100 + y)


def net(board, name):
    """Give every isolated conductor its own measurable net."""
    item = pcbnew.NETINFO_ITEM(board, name)
    board.Add(item)
    return item


def label(board, text, x, y):
    """Put identification on the drawing layer, never on milling copper."""
    item = pcbnew.PCB_TEXT(board)
    item.SetText(text)
    item.SetPosition(position(x, y))
    item.SetTextSize(vector(0.6, 0.6))
    item.SetTextThickness(pcbnew.FromMM(0.1))
    item.SetLayer(pcbnew.Dwgs_User)
    board.Add(item)


def component(board, reference, library, name, x):
    """Embed standard KiCad land patterns and save portable library copies."""
    footprint = pcbnew.FootprintLoad(
        str(SHARE / "footprints" / (library + ".pretty")), name
    )
    if footprint is None:
        raise RuntimeError("Missing standard footprint: " + name)
    footprint.SetFPIDAsString("Coupon20:" + name)
    footprint.SetReference(reference)
    footprint.Reference().SetVisible(False)
    footprint.Value().SetVisible(False)
    for pad in footprint.Pads():
        pad.SetNet(net(board, reference + "_" + pad.GetNumber()))
    save_footprint(footprint)
    board.Add(footprint)
    footprint.SetPosition(position(x, 2.5))


def save_footprint(footprint):
    """Use the native KiCad library writer."""
    plugin = pcbnew.PCB_IO_MGR.FindPlugin(pcbnew.PCB_IO_MGR.KICAD_SEXP)
    plugin.FootprintSave(str(ROOT / "Coupon20.pretty"), footprint)


def pair(board, index, width, gap, x, y):
    """Add parallel tracks with a specified edge-to-edge separation."""
    footprint = pcbnew.FOOTPRINT(board)
    footprint.SetFPIDAsString(f"Coupon20:Pair_W{width}_G{gap}")
    footprint.SetReference(f"T{index}")
    footprint.SetValue(f"W{width}_G{gap}")
    footprint.Reference().SetVisible(False)
    footprint.Value().SetVisible(False)
    footprint.SetAttributes(pcbnew.FP_EXCLUDE_FROM_BOM)
    layers = pcbnew.LSET()
    layers.AddLayer(pcbnew.F_Cu)
    layers.AddLayer(pcbnew.F_Mask)
    for row in range(2):
        conductor = net(board, f"W{width}_G{gap}_{row + 1}")
        local_y = row * (width + gap)
        for side in range(2):
            pad = pcbnew.PAD(footprint)
            pad.SetNumber(str(row * 2 + side + 1))
            pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
            pad.SetShape(pcbnew.PAD_SHAPE_CIRCLE)
            pad.SetSize(vector(width, width))
            pad.SetPosition(vector(side * TRACK_LENGTH, local_y))
            pad.SetLayerSet(layers)
            pad.SetNet(conductor)
            footprint.Add(pad)
        track = pcbnew.PCB_TRACK(board)
        track.SetStart(position(x, y + local_y))
        track.SetEnd(position(x + TRACK_LENGTH, y + local_y))
        track.SetWidth(pcbnew.FromMM(width))
        track.SetLayer(pcbnew.F_Cu)
        track.SetNet(conductor)
        board.Add(track)
    save_footprint(footprint)
    board.Add(footprint)
    footprint.SetPosition(position(x, y))
    label(board, f"{width}/{gap}", x + TRACK_LENGTH / 2, y - 0.65)


def preview(board):
    """Render saved copper polygons with a nominal 0.15 mm isolation ring.

    The background stays copper. This is a geometry illustration, not a CAM
    simulation or a guarantee of tool width on the physical machine.
    """
    scale = 80
    mask = Image.new("L", (WIDTH * scale + 1, HEIGHT * scale + 1), 0)
    draw = ImageDraw.Draw(mask)

    def pixel(point):
        return (round((pcbnew.ToMM(point.x) - 100) * scale),
                round((pcbnew.ToMM(point.y) - 100) * scale))

    for footprint in board.GetFootprints():
        for pad in footprint.Pads():
            polygon = pad.GetEffectivePolygon(pcbnew.F_Cu)
            for index in range(polygon.OutlineCount()):
                outline = polygon.COutline(index)
                points = [pixel(outline.CPoint(i))
                          for i in range(outline.PointCount())]
                draw.polygon(points, fill=255)
    for track in board.GetTracks():
        a, b = pixel(track.GetStart()), pixel(track.GetEnd())
        width = round(pcbnew.ToMM(track.GetWidth()) * scale)
        draw.line([a, b], fill=255, width=width)
        radius = width / 2
        for px, py in (a, b):
            draw.ellipse((px - radius, py - radius,
                          px + radius, py + radius), fill=255)
    expanded = mask.filter(ImageFilter.MaxFilter(25))
    copper = Image.new("RGB", mask.size, "#b87943")
    copper.paste("#eee3bf", mask=expanded)
    copper.paste("#cf955b", mask=mask)
    canvas = Image.new("RGB", (1220, 1220), "#f4f5f6")
    canvas.paste(copper, (130, 150))
    draw = ImageDraw.Draw(canvas)
    font_path = "C:/Windows/Fonts/arial.ttf"
    font = ImageFont.truetype(font_path, 23)
    title = ImageFont.truetype(font_path, 32)
    draw.text((130, 35), "PCB CNC / 12 x 11 mm / REV B", font=title,
              fill="#24313a")
    draw.text((130, 85), "Isolation only - unused copper remains",
              font=font, fill="#24313a")
    draw.rectangle((130, 150, 1090, 1030), outline="#24313a", width=2)
    for text, x in COMPONENTS:
        draw.text((130 + x * scale, 150 + 0.7 * scale), text, font=font,
                  anchor="mm", fill="#17232b")
    for width, gap, x, y in SAMPLES:
        draw.text((130 + (x + TRACK_LENGTH / 2) * scale,
                   150 + (y - 0.65) * scale),
                  f"W {width} / GAP {gap}", font=font, anchor="mm",
                  fill="#17232b")
    draw.text((130, 1070), "W = trace width; GAP = copper edge separation [mm]",
              font=font, fill="#24313a")
    draw.text((130, 1110), "Light grooves: nominal 0.15 mm. Labels are not milled.",
              font=font, fill="#24313a")
    canvas.save(ROOT / "validation/remaining-copper.png")


def verify(board, filename):
    """Measure widths, clearances and outline in the reopened native board."""
    measurements = []
    for width, gap, x, y in SAMPLES:
        tracks = [track for track in board.GetTracks()
                  if track.GetNetname().startswith(f"W{width}_G{gap}_")]
        assert len(tracks) == 2
        tracks.sort(key=lambda track: track.GetStart().y)
        assert all(track.GetWidth() == pcbnew.FromMM(width)
                   for track in tracks)
        separation = pcbnew.ToMM(
            tracks[1].GetStart().y - tracks[0].GetStart().y
        ) - width
        assert abs(separation - gap) < 0.000001
        measurements.append({"width_mm": width, "gap_mm": separation})
    edges = [item for item in board.GetDrawings()
             if item.GetLayer() == pcbnew.Edge_Cuts]
    points = [point for edge in edges
              for point in (edge.GetStart(), edge.GetEnd())]
    dimensions = [pcbnew.ToMM(max(getattr(p, axis) for p in points)
                              - min(getattr(p, axis) for p in points))
                  for axis in ("x", "y")]
    assert dimensions == [WIDTH, HEIGHT]
    assert len(list(board.GetFootprints())) == 7
    report = {
        "result": "PASS", "kicad": pcbnew.Version(),
        "outline_mm": dimensions, "pairs": measurements,
        "zones": len(list(board.Zones())), "physical_milling": "UNVERIFIED",
        "erc_and_parity": "N/A: passive board-only process coupon",
        "sha256": hashlib.sha256(filename.read_bytes()).hexdigest(),
    }
    (ROOT / "validation/geometry.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, indent=2))


def main():
    """Build the editable board and portable project, then reopen and check."""
    for directory in ("Coupon20.pretty", "validation", "manufacturing"):
        (ROOT / directory).mkdir(parents=True, exist_ok=True)
    board = pcbnew.BOARD()
    board.SetCopperLayerCount(2)
    board.GetDesignSettings().SetBoardThickness(pcbnew.FromMM(1.6))
    corners = [(0, 0), (WIDTH, 0), (WIDTH, HEIGHT), (0, HEIGHT)]
    for index, start in enumerate(corners):
        edge = pcbnew.PCB_SHAPE(board)
        edge.SetShape(pcbnew.SHAPE_T_SEGMENT)
        edge.SetStart(position(*start))
        edge.SetEnd(position(*corners[(index + 1) % 4]))
        edge.SetWidth(pcbnew.FromMM(0.05))
        edge.SetLayer(pcbnew.Edge_Cuts)
        board.Add(edge)
    component(board, "Q1", "Package_TO_SOT_SMD", "SOT-23", 2.7)
    component(board, "R1", "Resistor_SMD", "R_0805_2012Metric", 6.5)
    component(board, "R2", "Resistor_SMD", "R_0603_1608Metric", 9.75)
    for text, x in COMPONENTS:
        label(board, text, x, 0.7)
    for index, sample in enumerate(SAMPLES, 1):
        pair(board, index, *sample)
    board.GetDesignSettings().SetAuxOrigin(position(0, HEIGHT))
    board.GetDesignSettings().SetGridOrigin(position(0, HEIGHT))
    filename = ROOT / (NAME + ".kicad_pcb")
    pcbnew.SaveBoard(str(filename), board)
    project = json.loads((SHARE / "template/kicad.kicad_pro").read_text())
    project["meta"]["filename"] = NAME + ".kicad_pro"
    project["board"]["design_settings"]["rules"].update({
        "min_clearance": 0.5, "min_track_width": 0.5,
        "min_copper_edge_clearance": 1.0,
    })
    (ROOT / (NAME + ".kicad_pro")).write_text(
        json.dumps(project, indent=2) + "\n", encoding="utf-8"
    )
    (ROOT / "fp-lib-table").write_text(
        '(fp_lib_table (version 7)\n'
        ' (lib (name "Coupon20")(type "KiCad")'
        '(uri "${KIPRJMOD}/Coupon20.pretty")(options "")(descr "")))\n',
        encoding="utf-8",
    )
    reopened = pcbnew.LoadBoard(str(filename))
    verify(reopened, filename)
    preview(reopened)


if __name__ == "__main__":
    main()

# ---------------------------------------------------------------------------
# end of file
# ---------------------------------------------------------------------------
