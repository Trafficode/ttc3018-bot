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
  `project_cycle_lease`. `/measure` uses the same boundary but never cuts.
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
Project, Move and Profiles are the main navigation. Confirmed material setup
collapses to a summary. Desktop uses bounded forms, aligned parameter columns
and a preview next to the operation controls; mobile stacks the same controls.

Validation covers offline geometry/CAM, sender doubles and intercepted browser
actions. It does not replace an operator's physical tool, fixture and probe check.
