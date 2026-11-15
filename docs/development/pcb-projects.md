# Project-based PCB machining

The Project view selects a PCB project rather than a loose file. Tractor supplies
one revision-bound CAD ZIP with computed copper, semantic THT holes and outline.
The operator sets measured laminate thickness once and uses the permanent
**Ścieżki / Otwory / Obrys** selector.

Each stage is independent. A missing profile, absent THT holes or failed isolation
does not block preparing another stage. Profiles are created in Profiles before
starting the job; the Project view only selects a profile when several exist.
The main **Wykonaj etap** action captures one operator confirmation for one tool.
The server then prepares/validates CAM, probes Z and starts that tool's machining.
Preparation allows CNC disconnected or connected with a fresh Idle report. It never opens USB, disconnects, moves axes or changes zero.
Measured thickness remains editable with a freshly reported idle CNC connection.
Editing is locked during jobs/probes, preparation, pending commands or unknown
controller state. Entering a changed thickness clears the draft setup; the panel
prepares replacement stages while Idle. It never
disconnects the controller or changes a loaded machine program automatically.

The compact Project view shows the source layout and planned probe points as soon
as a package is selected, independent of CAM, thickness and a loaded NC job.
The material/XY toolbar, stage selector, preview and action panel fit a typical
landscape workstation. Mount the displayed tool, connect at the station, verify
the probe contact/release and press **Wykonaj etap**.
The existing confirmation dialog remains mandatory. Isolation offers 3–11 points
per axis (default 5×5, including rectangular grids), drilling uses a point, and
outline measures the eight perimeter points on intact copper outside the board.
The preview and confirmation use the selected grid. Changing its dimensions
requires a new matching map before Start; spacing must be at least 0.01 mm.
The single dialog explicitly authorizes spindle startup after successful CAM and
fresh Z. The permanently connected probe lead remains on the spindle housing.
Every drilling diameter still requires a physical tool change and another explicit
**Wykonaj etap** confirmation. Other stages never start automatically.

**Tylko pomiar Z** references and measures the source board area without needing
CAM or material thickness and never starts machining. Its diagnostic map has no
production job identity; executing a stage always measures again against the exact
validated program bounds. Outline measurement uses the selected mill-radius frame.
**Ponów przygotowanie** is a small secondary recovery action after CAM failure.

### Probe readiness and retry

The Project view lists every current condition preventing execution beside the
Start button. The same readiness result drives the disabled state and its text:
connection/fresh Idle, current coordinates, probe test/released input, live XY
datum, valid material/tool, source bounds, geometry and exact reduction approval.
Diagnostic measurement has its own smaller set of prerequisites. A failed older
cycle is historical evidence, not a permanent execution interlock. Recovery
details link to Move without moving or zeroing anything automatically.

Project execution and diagnostic probing authorize a first reference descent of
up to 10 mm below the current position, stopping at contact. The confirmation
shows current XY, start/target Z, limit and feed; work Z is not a measurement of
the physical air gap. Following a successful reference, every grid descent is
still capped at 1.4 mm from the measured clearance. Manual/legacy surface scans
retain their existing reference cap. All existing contact, modal, ownership,
coordinate and machine-state guards apply.

Project probes use G38.3. A missing contact is recoverable only after the controller
reports a coherent PRB success=0 at the commanded limit, acknowledges the command
and confirms fresh Idle, unchanged XY/WCO and a released probe. The probe and
cycle end without assigning Z or starting any machining. USB, XY, selected tool,
CAM and the still-connected probe-contact test remain available. The operator
corrects the position/circuit and starts a fresh cycle; incomplete maps are never
reused. There is no automatic retry, withdrawal or move on this outcome.
Unexpected ALARM/error, bad probe coordinates, timeout, Stop or lost heartbeat
still abort/reset/close as before because a stopped machine cannot be assumed.

`z_probe.attempt` retains phase (reference/grid), point number, start XYZ, target
Z, travel and feed in status/diagnostics. Failed-probe details show the old attempt
separately from current readiness. ALARM:5 means no contact in the programmed
travel, not a CAM rejection. The historical alarm can be acknowledged and clears
from the primary banner after genuine reconnection/contact-test recovery or a
new explicit start. It never grants a valid map or bypasses machine guards.

### Tight gaps and pad reduction

Project isolation first tries the original protected-copper contours. If they
cannot isolate the board, its isolated worker may compute a reduction candidate:
sampled boundary Voronoi territories share tight gaps at their approximate medial
line. The actual calibrated diameter and fixed depth do not change. The emitted
rounded NC is checked again: each original connected copper island must still
intersect exactly one remaining conductor, and different islands cannot share
one conductor. Erased islands, split conductors and remaining bridges block.
Only copper loss and inaccessible detail become warnings in this candidate.
This planar check does not certify pad annular rings, current capacity or assembly.

The secondary **Przygotuj podgląd** action computes a missing preview after
material/tool selection, including while CNC is disconnected; it never probes.
The preview overlays predicted removed copper in red and quantifies its area.
`report.padTrimReview` contains the source/profile/program-bound review ID.
If approval is absent, the execute cycle ends in inactive `review` phase before
loading or probing. The operator must inspect the preview, tick the reduction
approval and explicitly start again. Approval is not persisted as a reusable UI
preference. Changing setup, stock, profile or CAM clears it. Both project loading
and legacy progress loading require `acceptedPadTrim: {camId, reviewId}` matching
the exact immutable result. Loading records a timestamped acceptance and binds it
to the job metadata; Start checks that binding. The source CAD is untouched.
Wide gaps retain the original program without a reduction approval. Legacy CAM
remains strict unless explicitly requested with `allowPadTrim: true`. Geometry
parser checks, source/artifact hashes, operator lease, XY, Z and Stop gates remain.

One setup binds the source package, measured thickness and live G54 X/Y offset.
All stages must retain that X/Y datum. Position with Move, select the project,
and press **Ustaw tutaj zero X/Y** in the common material section. This single
explicit click writes the zero immediately; no extra dialog, navigation action
or retain-existing-zero alternative is shown. No disconnect/reconnect is needed.
XY can be set before thickness and before CAM has been computed. The first
thickness assignment and all three stage calculations preserve that datum.
Set XY writes only G10 L20 P1 X0 Y0; retain confirms the existing datum without
changing coordinates. Both require fresh Idle, G54, M5, unchanged position and
operator confirmation. Both invalidate Z and force reloading a prepared tool.
The datum is the lower-left finished PCB outline corner viewed from the machined
side (already mirrored for B.Cu), not the corner of a larger stock blank.
A live in-memory datum identity gates project loading, probing and Start.
Disconnect/restart/manual XY changes or observed XY-offset drift invalidate it;
Z-only reference changes preserve XY. Changing thickness never moves or zeros
axes; replacing an already prepared thickness creates a fresh setup and requires
its XY confirmation. Entering the first thickness after zero preserves XY.
Completed operations remain historical evidence for that setup; use a new setup
for another stock blank rather than reusing completion from the previous board. A refreshed page restores the
loaded project and stage. A service restart invalidates loaded/probe evidence.
Completion comes only from the exact sender job, never from a checkbox.

## API and persisted state

Operator-only routes require `X-PiloMill-Token`; POST requires same-origin JSON:

- `GET /api/pcb-projects/preview?packageId=<id>` returns cached source copper,
  outline bounds and semantic holes without toolpath calculation or CNC access.
- `GET /api/pcb-projects?packageId=<id>` returns recent setups in `runs`.
- `POST /api/pcb-projects/setup`: `packageId`. Creates empty material metadata
  (`thicknessMm: null`, no stages) without any machine commands. Shared by zero
  and CAM setup so simultaneous UI requests cannot create two active setups.
- `POST /api/pcb-projects/prepare`: `packageId`, optional `setupId`, `stage`,
  `thicknessMm`, `profileId`, `fingerprint`, optional `confirmedThroughCut`.
- `POST /api/pcb-projects/xy`: `setupId`, `mode: set|retain`, `position: [x,y,z]`,
  `confirmed: true`. The explicit zero button is the operator confirmation.
- `POST /api/pcb-projects/execute`: setup/stage, thickness, selected profile
  ID/fingerprint, current position, grid counts, `confirmed: true`,
  `fixed_probe: true` and through-cut approval when applicable. Returns the private
  `project_cycle_lease`. A reduction candidate additionally requires the exact
  `acceptedPadTrim` pair described above before any probing can begin. `/measure`
  never accepts reduction as authority to cut and never starts machining.
- CNC actions `project_cycle_heartbeat` and `project_cycle_stop` renew/cancel the
  cycle. Global Stop cancels preparation too; it cannot accidentally start probing.
- `POST /api/pcb-projects/load`: `setupId`, `stage`, `confirmedTool: true`, and
  fresh `confirmedThroughCut: true` for full-through outline profiles.

Setups live in the private application data `projects/` directory. Each stage
references an immutable CAM attempt. Source/profile/implementation/artifact
hashes remain checked before loading. The existing isolated CAM worker retains
private devices/network and resource limits. Connect and preparation share locks.
Loading itself never probes or starts a job. The new ephemeral project cycle
reserves the controller and owns the explicit preparation→probe→cut transition.
Only its originating browser receives a private lease. Lost ownership, Stop,
failed CAM/probing, stale position or changed datum/profile prevent progression.
The serial worker handles probe→cut without acquiring store/CAM locks; a bounded
background preparer uses store→CAM→CNC lock order and checks position/lease again.
Cycles and leases are never restored or resumed after service restart.
The library ingestion token cannot use these routes or control the machine.

## CAD import contract

`machining-project.json` schema 1 binds exactly three stage files to the source
board hash, side, shared absolute KiCad datum and Gerber-mm bounds. Each stage
has a file name and SHA-256. `tht-holes.json` has the same source hash and semantic
component-pad holes; vias and mechanical holes are excluded. Slots/unknown holes
disable only drilling. All geometry uses one transform, including B.Cu mirroring.
Path traversal, repeated ZIP members, oversized files, invalid coordinates and
changed hashes are rejected. Only warning-level `silk_overlap`, `silk_over_copper`
and `silk_edge_clearance` entries explicitly marked `informational: true` may
coexist with zero blocking issues. Copper/connectivity findings, errors, malformed
validation and failed independent Gerber readback still block production. Legacy archives require re-export for THT drilling.

Single-file NC import remains a separate entry from the project list. Existing
manual control and saved profiles remain available. Manual Zero and contact-test
settings live in the advanced Service disclosure (also reachable from NC import).
Project, Move and Profiles are the main navigation. Common material and XY setup
use a compact toolbar. Desktop uses bounded forms, aligned parameter columns
and a preview next to the operation controls; mobile stacks the same controls.

Validation covers offline geometry/CAM, sender doubles and intercepted browser
actions. It does not replace an operator's physical tool, fixture and probe check.

Measured project-map points show signed Z offsets in millimetres relative to
the initial reference touch, not relative to the first grid sample. Values
appear as samples arrive and remain available after completion. Unknown points
stay blank. Readback is bound to the project cycle, sender job and grid;
retained invalid-map readings are marked historical. Dense maps scroll locally
to keep labels readable, and a collapsed list exposes numeric readings.
