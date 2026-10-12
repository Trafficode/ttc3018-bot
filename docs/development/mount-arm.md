# PiloMill-L stand: Fusion-only workflow

## Source and checkpoint

Edit the saved **PiloMill-L** document in Autodesk Fusion's **Default Project**.
Do not edit or regenerate it in FreeCAD. Current revision:
`sliding-thread-insert-top-ribs-v2`.

Files under `mechanical/mount-arm/fusion/`:

- `PiloMill-L.f3d`: authoritative native checkpoint.
- `PiloMill-L.step`: solid exchange export, not the editing source.
- `validation.json`: dimensions, clearances, hashes and untested fits.
- `checkpoint_fusion.py`: validate and refresh the active saved Fusion document.

The checkpoint expects this checkout at `D:\Workspace\github\ttc3018-bot`.
Preserve unrelated work and inspect the active document before editing.
The exported archive was reopened and checked for four solid components.

## Four manufactured parts

1. **IntegralStand**: unchanged one-piece foot and upright. The foot is
   148 x 80 x 10 mm; the upright ends 220 mm above the bench. Its upper
   section is 40 mm wide and 8 mm thick; the reinforced lower root remains
   wider up to 70 mm. The front lip is 40 mm above the foot.
   Secure the foot externally to the CNC machine. Free-standing stability
   is not validated.
2. **EquipmentHead**: 130 x 105 x 4 mm plate with four Raspberry Pi (RPi)
   snap pegs and a top-open dovetail guide at the front edge. Print flat,
   underside on the bed, with the pegs facing up.
   Six top-side ribs are 3 mm wide and rise 4 mm above the plate. They stay
   outside the RPi board outline and clear the slide mouth, guide and pegs.
3. **ThreadInsert**: separate female M14x2 threaded ear, copied from the
   previous native solid, with a matching sliding tongue. Insert it from
   the front until the integral clip catches. The guide has a closed rear
   end. Press the clip through the underside release window to remove it.
   Print with its broad front face on the bed and threaded hole vertical.
4. **ClampKnob**: unchanged one-piece knob, 8 mm smooth neck and 16 mm
   threaded stem. Print knob-face down, stem up. No separate metal fastener.

The slide has provisional 0.3-0.35 mm clearance. Its 14 mm long, 1.5 mm
thick clip needs about 0.3 mm deflection. Neither its fit nor retention force
has been physically tested. Do not force or repeatedly flex the PLA+ clip.
Check the slide and thread by hand before installing the electronic board.
Hold the plate while loosening the knob; one knob releases height and tilt.

The original pivot remains local (65, 0, -18) mm. Its height range is
147-203 mm above the bench; the slot is 14.8 mm wide. The saved pose uses
182 mm pivot height and 25 degree tilt. Moving parts may exceed 220 mm.

## Electronics and fits

RPi board outline: 85 x 56 mm, centred at (65, 52.5) mm. Snap peg centres:
(46,28), (104,28), (46,77), (104,77) mm. The mounting pattern is offset
within the outline; install the board in the matching orientation.
Nominal peg neck: 2.35 mm; barb: 2.90 mm; split: 0.70 mm. Fit is uncalibrated;
never force the board. See the [official RPi 5 drawing](https://datasheets.raspberrypi.com/rpi5/raspberry-pi-5-mechanical-drawing.pdf).

The female thread preserves 1.03 radial scaling and the original 2 mm pitch.
Both threads are modeled, not cosmetic. BRep copies are not associative to
their historical thread or peg features. Test engagement and holding force.
Do not overtighten the printed threads.

Camera Rev 1.3 uses hot glue and a 145 mm ribbon. The DHT22 board is
16 x 41 mm; the planned auxiliary board is 40 x 60 mm. Cable routing,
camera coverage, heat, vibration and electronics keep-outs need physical checks.

## Two printing projects

Target: Anycubic Kobra X, 0.4 mm nozzle, Anycubic PLA+, 0.20 mm layers,
5 walls, 30% infill, 5 top/bottom layers and 5 mm automatic brim.

1. `print/01-PiloMill-RPi-zebra-i-pokretlo.3mf`: ribbed plate, insert and
   knob, approximately 2 h 8 min and 77 g. Filament 2 is grey PLA+.
   Supports are disabled; the revised dovetail flanks are 45-degree ramps.
2. `print/02-PiloMill-podstawa-i-stojak.3mf`: unchanged integral stand,
   approximately 4 h 45 min and 165 g, without supports.

Paths are relative to `mechanical/mount-arm/`. The first project was checked
in the slicer preview. Verify physical ACE slot 2 in the manual print-start
dialog. No job was uploaded or started. The previous upright-plate and
combined projects are obsolete for the new plate and retained outside Git.

The guide, clip, peg and thread fits, layer strength and slot-roof bridge
still need a first physical trial. CAD and slicing checks are not production
approval. Never start printer or CNC work without operator authorization.

The previous flat plate bowed after removal while still warm. The ribs are
an untested stiffness improvement, not proof that warping is eliminated.
Let the part and bed cool completely to room temperature before removal.
Avoid bending the part while releasing it. The board, sensor and cable
clearances still require a trial assembly with the user's actual hardware.
