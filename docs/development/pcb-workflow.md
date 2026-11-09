# Guided PCB workflow

The source-package panel now offers **Wykonaj PCB**: isolation, drilling by exact
source diameter, then a retained outside outline. Computer-aided manufacturing
(CAM) runs in the existing offline sandbox. It never opens USB or starts motion.

## Setup and output

Enter measured laminate thickness for every new job. The form never restores that
field automatically. Select a named machining profile stored on the station;
the immutable CAM request captures its revision, V-bit calibration and accepted
tool/setup values. The normal job form has one numeric input: thickness.
Material and mounting details have an explicit expanding arrow and information
buttons. Optional skin/retention overrides apply to that job only.

Configure feeds, spindle scale, tools and backing once in Profiles, not on every
board. Feed/spindle settings have no cutting defaults: supply the values for the
actual tools. Previous browser preferences can prefill a draft but require an
explicit review and save before use. See [machining profiles](pcb-profiles.md)
for parameter ownership, persistence and API details.

The initial mechanical engine supports round Excellon holes, grouped into one
program per diameter from 0.3 to 4 mm, and the rectangular source outline with a
1 mm end mill. Slots and unknown parser warnings fail, rather than disappear.
The accepted Gerbonara 1.6.3 diagnostic about KiCad's explicit G90 command after
the header only describes command placement; other diagnostics still fail.
Coordinates use the exact isolation/outline transform, including the B.Cu mirror.

Drill tip depth includes laminate thickness, the conical tip height calculated
from diameter/point angle, and the requested full-breakthrough allowance. Backing
must cover that entry plus a 0.5 mm reserve. The outline tool centre is 0.5 mm
outside the finished rectangle. Axial passes end either at `thickness - skin`
(initial UI value 0.20 mm skin), or through the stock with four side-centred tabs.
Tabs use the entered span/height; cutter sweep reduces the effective retained
span near the tab boundaries. Thickness, tip-angle and uncertainty values are
operator inputs, not measured or approved by the application.

Only a complete passing isolation result produces selectable mechanical programs.
An isolation failure keeps the report and preview but blocks the whole sequence.
Hashes cover every NC file, request, source ZIP, implementation and final report.

## Operator transitions

One mounting and G54 XY datum apply throughout. Each tool change is explicit:
confirm the tool and electrical reference, load the current operation, prepare Z,
then use the existing separate confirmation and manual Start. Nothing starts
automatically when a previous phase finishes. Flat tools use their recorded
mechanical parameters and the existing Default profile, never V-bit compensation.
The application switches that profile only on the operator's explicit stage load.

Isolation requires a fresh grid of at least 3 by 3. Every drill change requires a
fresh successful one-point Z probe tied to the exact loaded job, with unchanged
work offsets. The drilling breakthrough allowance must cover the preceding map's
measured surface spread plus the declared uncertainty. Otherwise Start fails.

Outline probing uses eight points: corners and side midpoints in a 3 by 3 layout,
with the centre omitted. These lie on the still-continuous copper frame outside
the PCB. The setup requires at least 2 mm of supported blank beyond each edge,
safe clamps and verified electrical continuity. The centre is virtual only in
the interpolation lattice; it is never represented as a measured point. All
outline cutting lies on the measured boundary. Do not use arbitrary disconnected
PCB copper, holes or milled grooves as electrical references. A removable touch
plate with thickness compensation is not implemented by this flow.

The server requires the fresh matching map, correct perimeter mode, unchanged XY,
and original CAM parameters at Start. It rejects feed/depth overrides and repeated
Starts of a completed/stopped/failed flow operation. Reloading an incomplete stage
creates a new job and requires new Z preparation. Existing exclusive sender,
probe heartbeat, confirmation, pause/stop and surface-offset checks remain active.

## Persistence and API

The final report includes `sequence` and `material`. Programs are stored beside
the immutable isolation result. `progress.json` is separate mutable execution
evidence, with exact sender job IDs, completion events and the original XY offset.
Only an actually completed matching job in this server session advances progress.
Browser closure does not mark completion. Restart or file replacement requires
reloading the unfinished operation. Manual checkboxes cannot skip a phase.

Operator routes, with the existing token and same-origin POST checks:

- GET `/api/cam/flow/:id`: progress, updated from sender completion.
- POST `/api/cam/load-stage`: id, index, confirmedTool, confirmedReference.
- POST `/api/cam/prepare`: source identity, calibrated-profile fingerprint,
  `processProfileId`, `processFingerprint`, `material` and explicit confirmations.
  The server resolves saved tool values; browser tool overrides are ignored.

The collection ingestion token cannot access these routes. The old isolation-only
API remains compatible; the UI now prepares full PCB requests. Existing completed
isolation results remain history and become stale when implementation hashes change.
Changed machining profiles mark their results stale and block both loading and
Start, including a program already loaded before the profile was edited.

## Verification limits

Tests cover real Gerber/Excellon fixtures, mirror/datum, drill grouping, drill-tip
depth, outside offset, pass depths, skins/tabs, missing thickness, thin backing,
eight-point interpolation, sender-based progress and fresh-Z Start gates. Target
acceptance generates all operations in the actual sandbox with CNC disconnected.
No physical probing, spindle or cutting acceptance has been performed. The
Miniroom isolation findings still block production preparation; this change does
not alter native PCB geometry or grant manufacturing approval.

On 2026-11-09, all 144 Python tests passed on the target, together with the
controller UI, surface-map, eight-point flow and PWA lifecycle JavaScript checks.
The actual private-device worker generated a four-operation fixture (isolation,
two drill diameters, outline) in approximately 0.18 seconds. This small-fixture
timing is not a full-board benchmark. No program was loaded into the real sender.
Browser checks at 1440 by 1024 and 390 by 844 verified required thickness, depth
calculation, retention selection, stage loading, point-Z gating and the eight-point
outline view. Execution/probe states used intercepted HTTP and actual worker
reports; physical-action POSTs were intercepted and none were attempted.
The active-step panel links directly to the existing map/zero preparation views.
The header shows the mechanical operation's actual CAM depth rather than the
Default V-profile depth. No page errors or horizontal overflow were found.
Scoped deployment compared source hashes, tested a separate tree, backed up every
replaced file and restarted only a disconnected station with an empty job.
The milling and relay HTTPS endpoints both continued to return HTTP 200.

The later compact-UI/profile change passed 152 Python tests and desktop/phone
browser checks. A saved recipe was also resolved into a real offline-worker
fixture with four operations; station profiles and the sender were untouched.
