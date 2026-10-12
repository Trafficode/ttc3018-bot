# CNC PCB process coupon — 10 × 10 mm

This smaller printed circuit board (PCB) coupon is the first machining sample.
It contains only width tests, clearance tests and one octagonal drilled pad.
The [40 mm coupon](pcb-cnc-coupon-40mm.md) remains available for later testing.

[KiCad project](../../reference/pcb-cnc-coupon-10mm/cnc-coupon-10mm.kicad_pro),
[board](../../reference/pcb-cnc-coupon-10mm/cnc-coupon-10mm.kicad_pcb),
[layout](../../reference/pcb-cnc-coupon-10mm/validation/layout.png) and
[CAM inputs](../../reference/pcb-cnc-coupon-10mm/manufacturing/).

## Layout

Viewed from the top, the three rows run from top to bottom:

| Row | Left: copper track width | Right: copper-edge clearance |
| --- | --- | --- |
| 1 | 0.2 mm | 0.2 mm |
| 2 | 0.5 mm | 0.5 mm |
| 3 | 0.7 mm | 0.7 mm |

Each left-hand trace joins two 0.8 mm square probe pads over a 2.5 mm
centre-to-centre span. Each right-hand pair consists of two independent copper
bars, 3 × 0.4 mm. Check continuity of each left trace and isolation between each
right pair. This samples horizontal tracks and vertical clearances only.
The 0.2 mm row is an intentional experimental limit, not a production default.
An effective cutter width greater than the gap cannot machine that gap faithfully.

V1 is a regular octagonal pad, 2 mm across flats, with a 0.8 mm round hole.
Its minimum copper ring is 0.6 mm. Copper exists on both sides only at this pad;
all other test features are on F.Cu. It represents a manual wire via: milling and
drilling do not plate the hole. Solder wire on both sides if testing an actual
layer connection. Machining only the front is enough to test the front pad shape.

Labels are on Dwgs.User for the screen/paper map. They are absent from copper
Gerbers and will not be milled. White in the map does not mean clearing all
copper: use isolation contours in CAM (computer-aided manufacturing), the step
that calculates tool movements.

## Datum and operations

All Gerbers and the metric Excellon drill file use the same plot origin at the
lower-left outline corner. Export is unmirrored. Outline coordinates span X/Y
0..10 mm; the hole centre is X=3, Y=2 mm. Set work X/Y at this corner, or apply
one identical intentional offset to every CAM operation. Preserve origin when
importing individual files; do not independently centre or zero their extents.

The nominal board thickness is 1.6 mm, not a measurement of the user's stock.
Use a larger blank, the supplied clamps and flat sacrificial backing. Keep
clamps outside all toolpaths and secure the coupon throughout machining.

Requested sequence: first make a shallow visible square border, then isolate
the test copper. Drilling is omitted from this first job. The border remains shallow enough to
keep the coupon attached. If cutting out the finished board, do that last with
tabs or another verified retention method. Edge.Cuts defines the finished
10 × 10 mm boundary; it does not specify depth, order or retention. In CAM,
cut-through tool compensation must be outside that boundary, not centreline.
Review any first-pass marking path separately for the chosen cutter width.

Prepared G-code and the first-coupon assumptions are documented in
[the CAM recipe](pcb-cnc-coupon-10mm-cam.md). Physical operation is unverified.

## Validation and reproduction

KiCad 10.0.6 native API generated and reopened the board. Saved geometry checks
confirmed its 10 × 10 mm outline, three exact widths and clearances, octagonal
pad, drill and origin. Design rules check (DRC) reports zero violations and
zero unconnected items under explicit 0.2 mm test rules and 1 mm copper-to-edge
clearance. No rule exclusions were added for these samples. Template ignored
checks remain recorded in the DRC JSON. No copper zones are present.
Electrical rules check, schematic parity and simulation do not apply to this
passive board-only coupon.

The exported copper contains the eight-vertex pad, and the drill output has a
single 0.8 mm hole at (3, 2). The four Gerber outline segments span 10 mm in
both axes. The native layer preview was rendered and visually inspected.
Source hashes and tool versions are in
[geometry.json](../../reference/pcb-cnc-coupon-10mm/validation/geometry.json);
[drc.json](../../reference/pcb-cnc-coupon-10mm/validation/drc.json) records DRC.

Run `reference/pcb-cnc-coupon-10mm/tools/build_coupon.py` with the installed
KiCad Python. It reuses the reviewed helper module from the 40 mm coupon without
modifying that project. Then run from the new project directory:

```text
kicad-cli pcb drc --format json --severity-all --all-track-errors --exit-code-violations --output validation/drc.json cnc-coupon-10mm.kicad_pcb
kicad-cli pcb export gerbers --layers F.Cu,B.Cu,Edge.Cuts --use-drill-file-origin --no-x2 --output manufacturing/ cnc-coupon-10mm.kicad_pcb
kicad-cli pcb export drill --drill-origin plot --excellon-units mm --output manufacturing/ cnc-coupon-10mm.kicad_pcb
```

Record measured track widths, residual copper, continuity/isolation readings and
hole centring together with the real tool and cutting settings. A successful
software check does not establish the machine's achievable accuracy.
