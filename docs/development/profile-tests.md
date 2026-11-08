# Fixed-depth profiles and isolation tests

The **Profile** tab has one profile selector and two views: **Ustawienia** and
**Test profilu**. Settings expose direct creation, editing, deletion and export;
there are no history-based creation controls or nested per-profile panels.
**Serwis** is an independent five-point experiment: its tool,
depth, widths and speeds are entered manually and never use the selected
profile's correction. Changing profiles does not invalidate a service map.

## Profile data

New profiles contain a fixed positive `depth` in millimetres, tool conditions,
calibration observations, fitted width model, unique ID and fingerprint.
The cutting Z before height compensation is `-depth`. The single-observation
calibration depth is separate from the desired cutting depth. Both are visible
inputs. The latter must fall inside the model's valid range and produce a
positive effective diameter. **Utwórz i wybierz profil** saves and selects a new
profile. Parameter dropdowns offer presets plus an explicit custom-value option.

Selecting an existing profile loads its editable parameters. **Zapisz zmiany**
updates that list entry atomically, retains its ID and changes its fingerprint.
The previous data is retained in the internal `revisions` collection (up to
100 snapshots), outside the UI and status payload. Earlier CAM fingerprints
then fail matching; regenerate CAM after editing. **Usuń profil** requires
confirmation and allows deleting the selected profile, switching to Default
and invalidating its test/file maps. Default cannot be edited or deleted.
Older profiles without `depth` can be opened in Settings and saved directly.
The readonly Default test uses 0.1 mm / 30 degrees,
depth 0.05 mm, XY F100, Z F20 and S300 without width correction.

The Z entry feed is the vertical speed when lowering the tool into material,
distinct from horizontal XY feed. The UI explains that F20 moves 1 mm in three
seconds. Spindle S is the controller scale, not measured RPM. Preset dropdowns
and their units/help text expose these meanings alongside each field.

## Manual motion and Z zero

Manual jog defaults to 300 mm/min. The standalone Z-zero search accepts
0.1–10 mm, with F10–60 and its existing explicit confirmation, heartbeat and
contact validation. The initial selection remains 1 mm. A 10 mm maximum is
a search distance, not a milling depth. Surface/service/profile-test mapping
retains its separate 1.4 mm maximum search distance.

Contact diagnostics are retained when observed during manual motion, then
remain valid after release and return to Idle. Idle polling is 100 ms so brief
contact is less likely to be missed. The input must still be open at start.
The zero panel explains the exact remaining blocker: connection, fresh report,
Idle, outstanding operation, contact verification/release, input ranges or
missing coordinates. A contact test never bypasses any other start guard.

For new named profiles, uploaded NC must use the exact saved cutting depth,
matching profile metadata, feeds and S. Depth/feed overrides are rejected.
The check runs before surface compensation; local Z correction does not
change the intended penetration below the measured surface. Existing untagged
NC still uses the legacy Default workflow.

## Test pattern

The test contains three parallel 10 mm copper strips of widths 0.3, 0.5 and
1 mm and two copper octagons with opposite-vertex diameters 1 and 2 mm.
Only closed isolation contours are generated, using G1 straight segments.
Unused copper is retained. There are no drilling or laminate cut-through moves.

The probe rectangle is the exact bounding rectangle of the tool's full
predicted sweep, with 1 mm added at each edge. There is no minimum 10 x 10 mm
square. All paths and copper shapes are translated together so the lower-left
sweep boundary is at local X=1, Y=1. Strip spacing grows when tool diameter
requires more room. Both rectangle dimensions and predicted groove width are
shown before probing; fields over 20 mm are rejected. Preview, nine probe
points and G-code share the same paths and rectangle. The SVG canvas also
follows the rectangle's aspect ratio rather than keeping a square empty area.

The initial X/Y is the lower left of the displayed probe rectangle, not the
edge of the first copper strip. Keep that whole field over fresh copper and
clear of clamps. A subsequent field advances by its height plus 1.5 mm in Y.
Check **Nowy test od aktualnego X/Y** after changing position or material.

## Operator flow

1. Select a profile on the top bar and inspect the fixed conditions and pattern.
2. Set the existing material zero. Place Z between 0 and 3 mm, verify probe
   contact and reopen the clips. Check clearance over the full rectangle.
3. Explicitly confirm **Zmierz 9 punktów Z**. The controller visits a serpentine
   3 x 3 grid using the existing probe guards. It never rewrites the work zero.
   Probing is F20 from Z=1 to Z=-0.4: maximum search travel 1.4 mm.
4. Inspect signed Z samples relative to existing Z=0. The cut uses bilinear
   height interpolation within that grid, with no extrapolation.
5. Remove the clip and cable from the tool, check the checkbox and separately
   confirm **Frezuj test profilu**. Mapping never starts milling automatically.
   The map is consumed after starting; retries require a fresh field/map.

The original uploaded job has its own runner and is never replaced by this
test. One probe/runner owns the serial stream at a time. Session, profile,
position, work offset and map validity are checked before execution. Changing
the selected profile invalidates the test map. Lease heartbeats and global
Stop use the existing operator controller. No software validation claims a
measured physical milling accuracy.

## Rapid vertical approach and manual finishing

Profile tests use the full rapid XY clearance (nominal 2 mm plus the map's
highest positive height). After XY reaches a contour, a separate vertical G0
descends to the interpolated local surface height plus 0.5 mm. From there,
the profile's plunge feed descends to the unchanged cutting depth. This
optimization is applied only while compiling the mapped profile test. It does
not change manual jog, probing, service coupons or uploaded NC programs.

After confirmed completion, the panel offers **Powtórz przejazd wykańczający**.
The operator can clean and inspect the PCB with spindle stopped, then confirm
unchanged material, clamping, tool, zero and removed probe cable. A separate
dialog starts exactly one additional pass, using the same profile and depth.
No pass starts automatically and no additional cutting depth is added.

The service retains an immutable in-memory copy of the already compensated
execution, map area, work offset and profile configuration. Replay does not
run CAM or compensate Z again. Before each start it checks the completion
state, repeat/session/profile identity, current position, Idle, open probe,
modal G54/G21/G90/G94/M5 and the live combined work offset. Place the tool
above the saved map rectangle at work Z between 0 and 3 mm before repeating.

Disconnect/reset, work-zero/profile changes, new probing or a different
production program invalidate replay. A failed/stopped pass cannot be replayed
through this control. Hardware/tool/material changes cannot be detected solely
in software; the operator must confirm their continuity. Completed pass count
is displayed. Extra passes do not create duplicate calibration observations.
Replay is ephemeral: service restart loses its captured execution and map.

## PC CAM

Export a named fixed-depth profile and run:

```powershell
python scripts/calibration_cam.py profile.json
```

The helper prints effective tool diameter, fixed cutting Z, feeds and S.
Supplying a different `--depth` is rejected. Regenerate the toolpath on the PC
with these values, then tag the final linear file using the existing explicit
`--tag final.nc --output final-profile.nc --confirm-cam-profile` command.
The marker asserts the operator used the specified CAM tool diameter; it does
not prove XY provenance or transform an existing path.

## Validation

`python -m unittest discover -s tests -p 'test_*.py'` includes simulated
nine-point contacts, preservation of work zero, profile/mode/clip interlocks,
exact copper dimensions, tool-sweep coverage, immutable versions and fixed
CAM depth. Browser validation uses a loopback fixture at 1440 x 900, 390 x 844
and 360 x 740. It covers independent service inputs, fixed test parameters,
preview, nine measured values, separate confirmations, one explicit cut and
revision creation. All physical probing and cutting remain operator actions.
