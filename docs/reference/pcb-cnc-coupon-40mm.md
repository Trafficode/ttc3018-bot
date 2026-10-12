# CNC PCB process coupon — 40 × 40 mm

## Purpose

Determine practical printed circuit board (PCB) isolation-milling limits before
choosing production rules. The coupon has no power input or functional circuit.
It tests copper continuity, isolation, drilling and hand soldering separately.

[Native KiCad project](../../reference/pcb-cnc-coupon-40mm/cnc-coupon-40mm.kicad_pro)
and [layout map](../../reference/pcb-cnc-coupon-40mm/validation/layout.png).
Units are millimetres; reference view is top copper, without mirroring.

## Test map

Rows run from top to bottom: **1.0, 0.8, 0.6, 0.5, 0.4, 0.3, 0.25, 0.2**.

| Region | Geometry | Measurement |
| --- | --- | --- |
| W1–W8, left | 9 mm centre-to-centre traces with 1.3 mm probe pads | Continuity, actual width, edge quality |
| G1H–G8H, centre | Two 7 × 0.6 mm copper bars per row | Isolation across the labelled copper-edge gap |
| G1V–G8V, right | Two 0.6 × 2 mm copper bars per row | Same gap after a 90-degree orientation change |
| R1–R3 | Standard 0603 imperial / 1608 metric, 0805 and 1206 pads | Pad survival and soldering with real components |
| U1 | SOIC-8, 1.27 mm pitch | Adjacent-pad isolation and solder bridging |
| J1 | Two-pin header, 2.54 mm pitch, 1 mm holes | Header fit and pad adhesion |
| D1–D4 | 0.6 / 0.8 / 1.0 / 1.2 mm holes; 0.6 mm annular rings | Drill fit, centring and pad survival |
| D5–D8 | Same holes; rings 0.25 / 0.35 / 0.45 / 0.6 mm | Sensitivity to drilling error |
| F1–F4 | 0.6 mm copper dots, centres forming a 36 × 36 mm square | X/Y scale, squareness and diagonal comparison |
| O1 / XY0 | 0.6 mm copper dot at local (5, 5) | Optional operator datum |

The ideal fiducial-square diagonal is approximately 50.912 mm. Measuring tiny
dot centres needs suitable magnification; a caliper reading is not enough to
claim fine positional accuracy. All copper bar pairs and unused component pads
are independent nets. Do not expect continuity between adjacent pads or bars.

The two clearance orientations sample X- and Y-facing edges. Width traces are
horizontal; the coupon is not an exhaustive test of vertical tracks, all corners,
all board positions or double-sided registration. Repeat measurements elsewhere
on a larger blank if the first test passes.

## Preparation and comparison

Use the existing clamps for the first test; no printed fixture is needed.
The blank must extend beyond the coupon to leave room for clamps and tool
clearance. Support the entire laminate on a flat sacrificial backing. Do not
machine the metal table. Material thickness 1.6 mm in the project is nominal;
measure the actual blank before CAM preparation.

Establish X/Y on a physical mark before milling. XY0 offers a consistent datum,
but another point is valid if CAM uses the identical origin. KiCad's top view has
positive Y downwards; verify the CAM-to-machine orientation rather than copying
editor coordinates directly. No G-code is supplied or executed.

Record material, copper thickness, tool tip/angle, runout observation, cutting
depth, feed, spindle setting, mounting method and date. Depth matters for V-bit
isolation width. A failure at 0.2 mm does not by itself identify a machine fault:
the tool geometry or CAM may be unable to generate the requested gap.

Do not cut the outline first. Preserve the outside stock while milling traces
and drilling. Later CAM preparation must define tabs or another method that
holds the coupon after cutting. Treat silkscreen labels as a paper/screen map;
they are not in F.Cu and will not appear on isolation-milled copper.

## Acceptance and results

1. Inspect under magnification before soldering; look for residual copper,
   burrs, broken tracks, lifted pads and off-centre holes.
2. Check each W trace for continuity. Check every G pair for isolation.
   Record meter readings, not just the continuity beeper result.
3. Check adjacent SMD pads for isolation. Trial-solder real 0603, 0805 and
   1206 components only after recording the bare-board results.
4. Check hole fit with the intended lead or gauge and inspect annular rings.
5. Repeat the coupon at least three times with documented settings.

Start operational designs at 0.5 mm width and clearance, with 0.4 mm as the
conservative lower reference. The smaller coupon fields are intentionally
experimental and must not silently become production defaults. Select a margin
above the smallest consistently successful width and clearance independently.
An empty results template is included beside the native project.

## Rebuild and validation

Run `tools/build_coupon.py` with the installed KiCad 10 Python executable, then
`tools/verify_coupon.py`. The generator uses the installed native API, project
template and standard footprint libraries. It does not modify KiCad installation
files, configure a machine or operate hardware.

The revision A validation used KiCad 10.0.6. DRC reported no violations and no
unconnected items under explicit 0.2 mm experimental rules. Native geometry
was reloaded and measured; source hashes are in `validation/geometry.json`.
Electrical rules check, schematic parity and simulation are not applicable:
there is no schematic or functional electrical circuit. Bench capability remains
unverified until a physical coupon is made and measured.

References: [KiCad 10 documentation](https://docs.kicad.org/10.0/en/pcbnew/pcbnew.html)
and the project's pinned CNC design rules. Validation does not waive operator
approval or dust-control requirements for the selected laminate.
