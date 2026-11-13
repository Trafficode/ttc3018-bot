# Project-based PCB machining

The Project view selects a PCB project rather than a loose file. Tractor supplies
one revision-bound CAD ZIP with computed copper, semantic THT holes and outline.
The operator sets measured laminate thickness once and uses the permanent
**Ścieżki / Otwory / Obrys** selector.

Each stage is independent. A missing profile, absent THT holes or failed isolation
does not block preparing another stage. Profiles are created in Profiles before
starting the job; the Project view only selects a profile when several exist.
Preparation runs automatically with CNC disconnected and never opens USB.

The three visible phases are preparation, Z measurement and machining. Mount the
displayed tool, connect at the station, check the probe contact and request Z.
The existing confirmation dialog remains mandatory. Isolation measures a 3×3
surface map, drilling uses a point, outline measures the eight perimeter points.
Start appears separately after measurement; nothing starts automatically.
Each drilling diameter requires its own tool change and fresh Z measurement.

One setup binds the source package, measured thickness and live G54 X/Y offset.
All stages must retain that X/Y datum. Changed X/Y blocks loading another tool;
prepare a new setup after repositioning stock. A refreshed page restores the
loaded project and stage. A service restart invalidates loaded/probe evidence.
Completion comes only from the exact sender job, never from a checkbox.

## API and persisted state

Operator-only routes require `X-PiloMill-Token`; POST requires same-origin JSON:

- `GET /api/pcb-projects?packageId=<id>` returns recent setups in `runs`.
- `POST /api/pcb-projects/prepare`: `packageId`, optional `setupId`, `stage`,
  `thicknessMm`, `profileId`, `fingerprint`, optional `confirmedThroughCut`.
- `POST /api/pcb-projects/load`: `setupId`, `stage`, `confirmedTool: true`, and
  fresh `confirmedThroughCut: true` for full-through outline profiles.

Setups live in the private application data `projects/` directory. Each stage
references an immutable CAM attempt. Source/profile/implementation/artifact
hashes remain checked before loading. The existing isolated CAM worker retains
private devices/network and resource limits. Connect and preparation share locks.
Loading never probes or starts a job; the existing sender owns those interlocks.
The library ingestion token cannot use these routes or control the machine.

## CAD import contract

`machining-project.json` schema 1 binds exactly three stage files to the source
board hash, side, shared absolute KiCad datum and Gerber-mm bounds. Each stage
has a file name and SHA-256. `tht-holes.json` has the same source hash and semantic
component-pad holes; vias and mechanical holes are excluded. Slots/unknown holes
disable only drilling. All geometry uses one transform, including B.Cu mirroring.
Path traversal, repeated ZIP members, oversized files, invalid coordinates and
changed hashes are rejected. Legacy archives require re-export for THT drilling.

Single-file NC import remains a separate entry from the project list. Existing
manual control and saved profiles remain available.

Validation covers offline geometry/CAM, sender doubles and intercepted browser
actions. It does not replace an operator's physical tool, fixture and probe check.
