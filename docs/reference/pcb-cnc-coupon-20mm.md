# Compact CNC isolation coupon

Native project: `reference/pcb-cnc-coupon-20mm/cnc-coupon-20mm.kicad_pro`.
Open the corresponding `.kicad_pcb` to inspect the layout. This is a passive
process coupon, not a functional circuit; it intentionally has no schematic.

## Geometry

The board is 12 x 11 mm, revision B, with top copper only. The original
20 mm project filename is retained so existing links still work. Standard KiCad 10
land patterns are embedded and copied into the portable `Coupon20.pretty`
library: `SOT-23`, `R_0805_2012Metric`, and `R_0603_1608Metric`.
Their pads are independently isolated and are intended for soldering tests.

Four independent pairs of parallel, 3.5 mm long track centre lines test:

| Position in top view | Track width | Edge-to-edge copper gap |
| --- | --- | --- |
| Upper left | 0.5 mm | 0.5 mm |
| Upper right | 0.5 mm | 0.7 mm |
| Lower left | 0.7 mm | 0.5 mm |
| Lower right | 0.7 mm | 0.7 mm |

Measure track width and separation in the straight central section.
Use continuity and isolation measurements before soldering components.

## Isolation milling

`manufacturing/` contains top-copper and outline Gerbers with a common
lower-left auxiliary datum. The top is viewed from above; do not mirror it.
CAM must retain unused copper and cut only narrow contours around the pads
and tracks. Do not select non-copper clearing, pocketing or full-area removal.
The copper left between two isolation grooves is intentional floating copper.
The specified gap is the distance between the two intended tracks; it is not
a command to remove all copper across that distance.

`cam/millproject` is a provisional pcb2gcode contour-only configuration using
the previous V30/0.1 mm tool assumptions. It has no wide isolation setting,
drill input or outline-routing input. CAM has not been run for this revision;
there is no machine-ready `.nc` file in this project. Generate and review the
toolpath against the current measured tool width before physical use.
`Edge.Cuts` is a reference boundary, not a request to cut through the laminate.

`validation/remaining-copper.png` illustrates nominal 0.15 mm grooves around
the saved KiCad copper. It is not a machining simulation. The actual groove
width depends on tool geometry, depth, runout and machine stiffness.
Labels are drawing annotations and will not be milled.

## Checks and regeneration

Run `tools/build_coupon.py` with the Python bundled with KiCad 10 and Pillow.
It creates the native board through the KiCad API, reopens it, checks all four
width/gap combinations and the outline, and renders the preview.
Re-export Gerbers and rerun KiCad DRC after rebuilding.

Validation: `validation/geometry.json` and `validation/drc.json`.
Electrical rules, schematic parity and circuit simulation do not apply to this
board-only process coupon. Physical milling and CAM generation are unverified.
