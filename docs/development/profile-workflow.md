# V-bit profile workflow

The Profiles panel shows Settings, Test and Calibration in one accordion.
Settings can persist a draft without observations. A draft can run profile
tests, but it cannot generate production CAM. Changing cutting conditions
returns the profile to draft and leaves its previous revision in history.

The test still requires operator confirmation, a local Z reference and a fresh
3 × 3 map on a 5 × 5 mm field. It contains 0.3 and 0.5 mm copper strips in each
orientation, horizontal at the top and vertical at the bottom. One or two
passes run as one job. The second path goes outward for
every shape, at an offset equal to the planned cutter width times one minus
the selected overlap. The map covers both passes and their cutter sweep.

Each new test reads the current saved revision and its selected pass options.
It regenerates the paths and applies a fresh Z map. Draft profiles calculate
groove width from the tip, full angle and depth; calibrated profiles use their
saved width model at the same depth. Feed and spindle settings control
cutting, but do not directly change the coordinates of the paths. A stale
profile revision is rejected before probing. The test preview identifies the
source of the width estimate and shows the active cutting settings.

Settings can specify a slower corner feed for the profile test. It applies
along the path for 0.5 mm before and after each turn on both passes. Short edges
covered by both zones use the slower feed throughout. An empty setting uses
the XY feed throughout. Editing this setting keeps the previous calibration
model and measurements. Production toolpaths continue to use the XY feed.

Calibration is tied to the most recent completed test for the exact profile
revision. The operator selects the strip by width and orientation, then enters
the copper strip or full groove measurement at 0.01 mm resolution. A strip
estimates the effective width from the planned spacing between the two sides. A single-pass groove gives
the width directly. For two passes, the operator confirms that they form one
continuous groove and the panel subtracts the planned offset between paths.
The second measurement is optional. If both estimates differ by more than
0.02 mm, the operator must confirm which estimate to use. Only the selected
measurement is stored and used for the model. A strip result is not labeled
as groove verification. Existing profiles made using both measurements
retain their old readings and model.

This workflow does not change pass options for production projects.
