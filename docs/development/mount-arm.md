# PiloMill-L stand: Fusion-only workflow

## Authoritative design

Use the saved **PiloMill-L** document in Fusion's **Default Project**. Edit this
active document, save it and update the repository checkpoint after each change.
Do not rebuild or edit this design in FreeCAD.

Repository files: `mechanical/mount-arm/fusion/`.

- `PiloMill-L.f3d`: native Fusion archive, including components and timeline.
- `PiloMill-L.step`: solid exchange export, not the editing source.
- `validation.json`: native geometry checks, parameter values and export hashes.
- `checkpoint_fusion.py`: trusted Fusion API script for saving the active design
  and refreshing those exports. Execute through the existing local Fusion MCP
  (Model Context Protocol) connection or Fusion's Scripts command. It does not
  modify geometry, install software or operate any connected hardware.
- `calibration/`: existing snap-fit test samples and their checksums. These are
  reference exports, not native Fusion components or calibrated hardware fits.

The checkpoint script currently expects this Windows checkout at
`D:\Workspace\github\ttc3018-bot`. Update its output path if the checkout moves.
It refuses unrelated documents and unexpected component structures. New parts
require updating these checks deliberately. Do not execute scripts from untrusted
sources; Fusion API scripts run with the user's permissions.

The existing local MCP endpoint can be obtained from Fusion's connection status.
Inspect the active document first, make scoped native changes, verify geometry and
timeline health, then save and export. Never substitute a freshly generated model
for the user's active document or discard unsaved work.

## Geometry and controls

Four stand components: base, upright, equipment plate and M5 knob. The upright is
flush with the rear base edge, making an L profile in side view. The base extends
forward only, underneath the equipment plate. Leave room behind the upright for
the knob. Base dimensions are 180 x 140 x 10 mm; upright is 50 x 235 x 8 mm.

The closed slot permits 70 mm of vertical adjustment. Pivot height is 147 to
217 mm above the bench; the saved pose uses 182 mm and 25 degree tilt. One knob
unlocks height and tilt together. Hold the plate while adjusting. Closed slot ends
do not protect against completely unscrewing the bolt.

The imported parts remain solid base features; they do not contain the old CAD
system's sketch history. The L conversion now has native Fusion sketches and
extrusions for filling the old socket and cutting the rear-edge socket, plus an
assembly position snapshot. New socket geometry uses named parameters:
`LBaseThickness`, `LSocketFloor`, `LSocketWidth`, `LSocketDepth`.

The rear-open socket has a 2 mm floor. Dry-fit and glue its tongue after testing.
Check withdrawal and bending strength with dummy weights. Use non-slip feet and
a secured ballast weight; moving the upright does not prove stability.

## Electronics and print assumptions

Raspberry Pi (RPi) 5 uses four prototype split snap pegs without screws. Nominal
mounting pattern is 58 x 49 mm with 2.7 mm holes. Peg shaft is 2.35 mm, barb
2.90 mm, tip 2.10 mm and split 0.70 mm. Assumed board thickness is 1.6 mm.
Print the calibration samples first; measure real holes and never force the PCB
(printed circuit board) onto tight pegs. PLA+ snaps can crack or creep.

Camera Rev 1.3 mounts underneath with hot glue, clear of lens, connectors and
conductors. RPi and camera move together; the user's ribbon is only 145 mm.
The DHT22 module, 16 x 41 mm, glues to the base. The planned 40 x 60 mm LED board
requires insulating spacers and metal heatsinking for power LEDs. These electronics
are not detailed native component models in the current archive.

Target material is PLA+ on Anycubic Kobra X. Base and upright print flat; knob
prints with its nut recess up; plate prints flat with pegs up. Pivot-hole supports
and peg strength require slicer inspection and coupons. Individual part envelopes
fit the nominal 260 mm build volume, not necessarily all parts on one plate.
Cosmetic surfaces are class B; mating and bed-contact surfaces are class C.

Use a metal M5 bolt and nut, with broad washers. Nut recess is an uncalibrated
8.3 mm across flats and 4.5 mm deep. Check hardware length, clamp holding force,
heat, vibration and cable loads physically. The printed plate is not a heatsink.

## Validation and removed files

The active Fusion L conversion has four solid components, source-equivalent
volumes, a flush rear edge and healthy timeline features. The socket sketches
are constrained. This is not a complete parametric reconstruction of all parts.
The native archive was reopened in Fusion and verified to contain four solids
and the timeline; the original saved document was restored as the active model.
Physical fit, joint strength, clamping force, stability, temperature limits,
camera coverage, cable routing and slicing remain unvalidated.

Obsolete iterations, native FreeCAD files and FreeCAD generation scripts have
been moved to an external recoverable backup, not kept as competing repository
sources. Historical reports and screenshots are not proof of current Fusion
validation. No machine, printer or Raspberry Pi actions occur in this workflow.
