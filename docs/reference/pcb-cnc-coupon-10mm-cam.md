# First 10 mm coupon CAM recipe

This recipe is a preliminary physical trial, not a calibrated production process.
Computer-aided manufacturing (CAM) generated the isolation from the current
[10 mm KiCad coupon](pcb-cnc-coupon-10mm.md). The operator starts all motion.

## Operator files

1. [01-air-check.nc](../../reference/pcb-cnc-coupon-10mm/cam/jobs/01-air-check.nc):
   spindle off, same X/Y paths as cutting, low passes at Z=+1 mm, retracts at +3 mm.
2. [02-copper-mark-and-isolate.nc](../../reference/pcb-cnc-coupon-10mm/cam/jobs/02-copper-mark-and-isolate.nc):
   enables the spindle, marks the square first, then isolates copper. No drilling,
   no through-cut, no coordinate changes and no tool change.

Use the first file before the second. Both use G54 with work Z=0 on the actual
copper surface and X/Y=0 at the square's lower-left corner. Paper thickness must
already be accounted for when setting Z. Do not change zero between the two files.
Load via the Bark Beetle File tab; upload only prepares the job. Start is a
separate operator action. Check that +X/+Y point into the available blank.
Keep the owner browser active; losing its heartbeat requests a feed hold.

Confirm the whole path is clear of clamps at Z=+3 mm, including the initial
move from the current position. Tool centres occupy X/Y=0..10 mm. The cutter
extends beyond those centres: the marking square has an approximately 0.069 mm
half-width outside its boundary. Use stock beyond the square. This is a visual
centreline border, not a dimensionally compensated board cut-out.

Inspect the air run before allowing cutting. Stop if actual positions, zero,
spindle behaviour or clearance differ from these assumptions. On the first
cutting attempt, inspect whether the shallow grooves fully remove copper before
changing any depth. A 0.2 mm failure may come from tool width, Z error or runout;
passing file validation does not prove milling capability.

## Provisional parameters

| Parameter | Value and interpretation |
| --- | --- |
| Tool | V-bit, 3.175 mm shank, assumed 30 degree included angle, 0.1 mm flat tip |
| Isolation Z | -0.05 mm relative to copper top |
| Isolation tool width | 0.126795 mm, calculated from the nominal tip and angle |
| Requested isolation width | 0.8 mm, multiple overlapping passes where space permits |
| Pass overlap | 50 percent of effective cutter width |
| Border Z | -0.07 mm; calculated width approximately 0.137513 mm |
| Horizontal feed | 100 mm/min |
| Plunge feed | 30 mm/min |
| Spindle command | M3 S1000, controller scale, not verified RPM |
| Spin-up wait | G4 P2 seconds |
| Retract height | +3 mm work Z; clearance must be checked physically |
| End | Retract to +3 mm, M5, M30 |

Width calculation: `tip + 2 * depth * tan(included_angle / 2)`. Actual tip wear,
runout and copper-surface unevenness can increase or vary the groove width.
The depth assumes thin copper, roughly 35 micrometres, and a flat mounted blank;
the actual copper thickness has not been established. No surface probing or
height-map compensation is included. S1000 must be appropriate for the existing
controller configuration; it does not establish the spindle's measured speed.
Feeds and depth need physical evaluation on the first sample.

The current job leaves the entire octagonal pad centre in copper. The hole shown
in the KiCad layout is a future drill feature and is not machined by these files.
Only isolation grooves are removed; white areas in the layout are not all cleared.

## Generation and adaptation

pcb2gcode 3.0.4, commit a5604c4, Gerbv 2.13.0 and Boost 1.83.0 generated
[isolation-raw.ngc](../../reference/pcb-cnc-coupon-10mm/cam/raw/isolation-raw.ngc)
using [millproject](../../reference/pcb-cnc-coupon-10mm/cam/millproject).
The portable release runs in Ubuntu 24.04 WSL without GEOS. Toolkit revision:
`b49f118ec6dc9237206e67b1a3710410133cecdf`.
No back layer, drill file or cut-through outline is passed to pcb2gcode.
Zero-start is disabled; the Gerber's shared origin is preserved.

[build_jobs.py](../../reference/pcb-cnc-coupon-10mm/tools/build_jobs.py) checks the
exact expected CAM startup/shutdown and allowed operation set. It replaces that
one reviewed tool-change envelope with an explicit single-tool G54 startup and
M5 shutdown. Unknown commands, different feeds/depths or changed envelope fail.
Every isolation-body movement, feed and dwell is retained. No generic command
deletion or coordinate shifting is performed. The square is an explicit four-side
centreline marking pass; it does not use the CAM cut-through outline operation.

The air variant retains all X/Y moves and feeds, omits spindle start, and replaces
negative marking/isolation Z with +1 mm. It ends with M5 and M30.

From the coupon `cam` directory, create `raw` if needed and run the local
`.local/pcb2gcode/run.ps1 --config millproject` wrapper using its repository path.
From the coupon root, run:

```text
python tools/build_jobs.py --validator PATH_TO_TTC_REPO/monitor/jobs.py
python tools/plot_jobs.py
```

The plot command uses PyMuPDF and the revision-matched native layout PDF.

## Evidence

Both complete files passed the actual Bark Beetle `parse_program` validator:
4958 commands for air, 4960 for cutting. Bounds are X/Y 0..10 mm; air Z +1..+3 mm;
cutting Z -0.07..+3 mm. Every XY rapid has a +3 mm retract, and all X/Y motion
segments match between files. There are no arcs, drilling cycles, M6, T words,
probing, homing, machine-coordinate moves or offset changes in either output.

[cam.json](../../reference/pcb-cnc-coupon-10mm/validation/cam.json) records bounds,
segments, checks and SHA256 hashes of the source Gerber, board, raw CAM file,
configuration, validator and final jobs. The
[toolpath overlay](../../reference/pcb-cnc-coupon-10mm/validation/toolpaths.png)
was visually inspected: blue is the border; red shows nominal cutter-width
strokes for isolation. This is not collision detection.

[remaining-copper.png](../../reference/pcb-cnc-coupon-10mm/validation/remaining-copper.png)
shows the simulated remaining copper, with removed areas in white and no hole.
The 0.2 mm test clearance remains intentional; extra passes are limited by the
neighbouring protected copper. Nominal planar sweep checking found ten separate
intended copper features, one connected background and zero isolated waste
islands. Maximum feature-area loss was 0.003868 mm2 under CAM's 0.002 mm tolerance.
See [sweep.json](../../reference/pcb-cnc-coupon-10mm/validation/sweep.json).
This model assumes flat copper and no runout. It does not certify real machining
or exclude every locally narrow part of the connected background.

The previous narrow single-pass recipe and jobs are preserved only in
`cam/archive/single-pass`; use the current `cam/jobs` files. The sweep check uses
Shapely 2.2.0 and Pillow via `tools/verify_sweep.py`.

No serial connection was opened, no program uploaded to the controller, and no
motion or spindle command executed during preparation. Physical acceptance
remains UNVERIFIED.
