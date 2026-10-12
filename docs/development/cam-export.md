# CAM export for Bark Beetle

Computer-aided manufacturing (CAM) turns KiCad Gerber copper and outline files,
and Excellon drill files, into tool movements. This document defines the export
contract for the current panel. It is not a tested pcb2gcode post-processor or a
calibrated cutting recipe. The validator in `monitor/jobs.py` remains authoritative;
see [file jobs](file-jobs.md) for its complete limits.

## Export contract

| Setting | Required output |
| --- | --- |
| Units and coordinates | Millimetres, absolute, feed per minute: G21 G90 G94 |
| Work coordinates | G54; preserve the same design origin across all operations |
| Toolpaths | Linear G0/G1; approximate curves with segments |
| Tools | One tool per file; no T words, M6 or operator-stop commands |
| Drilling | Explicit retract, XY positioning and G1 Z movements; no canned cycles |
| Initial motion | G0 to positive work Z only, then first XY move with both X and Y |
| Retracts | Above material and every clamp crossed by the tool |
| Spindle | Separate M3 S and M5; S is 0..1000 controller units, not verified RPM |
| Feed | Explicit F for cutting/plunging, within 1..300 mm/min |
| End | Retract, separate M5, then M2 or M30 |
| Other functions | No coolant, probing, macros, G53, G92 or controller settings |

Use a common origin marker in KiCad and CAM. Independently moving each output's
bounding box to zero can misalign copper, holes and the board outline. Octagonal
pads do not guarantee that their tool-offset paths contain no curves; check the
actual exported movements as well.

The effective engraving diameter, cut depth, plunge feed, horizontal feed and
spindle setting must be chosen for the real tool and material. A V-bit's effective
diameter depends on its tip and cutting depth. Do not substitute its shank diameter.
Board thickness and backing determine drilling and cut-through depths. Positive
work Z alone does not establish clearance over clamps.

## pcb2gcode preparation

The upstream manual documents these useful options: `metric=true`,
`metricoutput=true`, `nog64=true`, `nog81=true`, `nog91-1=true`, `nom6=true`,
`al-front=false` and `al-back=false`. They are only part of the required setup.
`nom6` does not prove that every tool word or multi-tool operation is absent.
Default exports may still include unsupported commands such as M9. Preambles do
not remove commands generated elsewhere in the file. Do not label an untested
configuration as a compatible GRBL post.

For each chosen CAM version, generate a small real Gerber/Excellon example and
inspect the output. Configure the post-processor to satisfy the contract. Reject
unsupported operations rather than blindly deleting commands or clamping F/S.
Then validate the entire output with `parse_program`, check its origin and tool
offsets against the design, and perform the supervised spindle-off acceptance
test before cutting. The first reviewed real Gerber export is documented in the
[10 mm coupon recipe](../reference/pcb-cnc-coupon-10mm-cam.md). Its physical
machining acceptance remains unverified.

Sources: [pcb2gcode manual](https://github.com/pcb2gcode/pcb2gcode/blob/master/man/pcb2gcode.1)
and [FlatCAM isolation workflow](https://flatcam.org/manual/iso.html).

## Spindle-off format example

[octagon-air-check.nc](../../examples/cam/octagon-air-check.nc) is a hand-written
format example, not a PCB isolation toolpath. It traces an octagon with eight G1
segments at work Z=5 mm, with a 10 mm by 10 mm XY bounding box. It contains no M3
and never lowers into material. It still commands real motion if an operator
starts it: establish work zero and verify travel and clearance first.

Validation only, from the repository root (does not access USB):

```powershell
python -c "from pathlib import Path; from monitor.jobs import parse_program; p=Path('examples/cam/octagon-air-check.nc'); r=parse_program(p.name,p.read_text(encoding='ascii')); print(r['bounds_mm'],r['max_feed'],r['max_power'])"
```

The example passes the current parser. CAM generation, mechanical clearance and
physical motion remain separate acceptance steps.
