# CNC PCB coupon — 40 × 40 mm, revision A

Open `cnc-coupon-40mm.kicad_pro` in KiCad 10, then open the PCB editor.
This is a passive board-only process coupon, not a powered circuit. No schematic,
machine job, feeds, speeds or fabrication acceptance are implied.

- [Test map and measurement procedure](../../docs/reference/pcb-cnc-coupon-40mm.md)
- [Layout preview](validation/layout.png)
- [Printable layout](validation/layout.pdf)
- [DRC evidence](validation/drc.json)
- [Measured native geometry](validation/geometry.json)

The width and clearance ladders cover 1.0, 0.8, 0.6, 0.5, 0.4, 0.3, 0.25
and 0.2 mm. Values below 0.4 mm are deliberately experimental. A clean DRC
with the coupon's 0.2 mm limits does not establish machining capability.

Top copper is the test surface. B.Cu contains only the native through-hole pad
rings; it is not a second-side test. KiCad's through-hole pad type does not mean
that CNC-drilled holes are plated. No electrical connection through the board
is assumed. No paste, silkscreen, mask or bottom-side machining is required.

The XY0 copper dot and auxiliary origin are 5 mm right and 5 mm down from the
top-left outline corner in the editor's top view. CAM must explicitly select
the same datum and axis convention; setting this origin is not a machine setup.
All labels are silkscreen-only reference annotations, not copper to engrave.

The custom diagnostic footprints are included in `CncCoupon.pretty`.
Standard footprints use the installed KiCad 10 libraries through `fp-lib-table`.
Scripts in `tools/` use KiCad's own Python runtime to rebuild and verify geometry.
Rebuilding replaces this generated coupon; save edited designs separately.

Use a larger blank held by the supplied CNC clamps. Keep clamps outside every
tool path. The 40 mm outline is the finished coupon, not a mandatory blank size.
Do not cut the outline until the final operation and a holding strategy exists.
