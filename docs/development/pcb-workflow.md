# Guided PCB workflow

The source-package panel offers **Wykonaj PCB**: isolation, drilling by exact
source diameter, outline, or selected operations. Computer-aided manufacturing
(CAM) runs in the existing offline sandbox. It never opens USB or starts motion.

## Setup and output

Enter measured laminate thickness for every new job. The form never restores that
field automatically. Select independent profiles for the requested tools.
The immutable CAM request captures their revisions and tool/setup values.
V-bit calibration is required only for isolation. The job form shows scope
and thickness; tool selections expand when needed.

Configure feeds and tools once in Profiles, not on every board. Supply XY/Z feed
for the actual tools. Preset dropdowns cover all profiles. Drilling has four
fields. Outline includes step-down in its basic fields (initially 0.2 mm) and has
no Advanced section. Tab width is automatic: max(3 mm, diameter + 2 mm). Both simple
mechanical profiles use fixed S1000 control and operator-verified tool/backing.
See [machining profiles](pcb-profiles.md)
for parameter ownership, persistence and API details.

The initial mechanical engine supports round Excellon holes, grouped into one
program per diameter from 0.3 to 4 mm, and the rectangular source outline with a
0.5–3 mm end mill. Slots and unknown parser warnings fail, rather than disappear.
The accepted Gerbonara 1.6.3 diagnostic about KiCad's explicit G90 command after
the header only describes command placement; other diagnostics still fail.
Coordinates use the exact isolation/outline transform, including the B.Cu mirror.

New drill tip depth is laminate thickness plus the entered tip overrun into
backing. The operator includes the entire point and required allowance in that
overrun and ensures adequate backing. There is no additional cone calculation
or automatic backing-thickness check. Old API recipes retain their previous
cone/allowance calculation until explicitly edited. The tool centre is one radius
outside the finished rectangle. Simple outline passes end at thickness minus
remaining material for a continuous skin, or thickness plus backing entry between
four side-centred tabs. The same remaining-material field sets tab height.
Full-through mode leaves no retained material. Cutter sweep reduces effective
bridge width near the boundaries. Thickness, overrun and retained material are
operator inputs, not measured or approved by the application.

When isolation is requested, its passing sweep check gates the whole sequence.
Mechanical-only jobs validate the board geometry without a V-bit model or an
isolation sweep claim. Output contains only the selected stages.
Full-through outline cutting requires explicit workholding confirmation.
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
work offsets. For new drilling profiles the operator's tip overrun includes the
required allowance; there is no separate uncertainty field or allowance gate.
Old API recipes keep the preceding-map spread plus uncertainty check.

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
  `operations`, `processProfiles`, `material` and explicit confirmations.
  The server resolves saved tool values; browser tool overrides are ignored.

The collection ingestion token cannot access these routes. The old isolation-only
API remains compatible; the UI prepares selected operations. Existing completed
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

The independent-tool update on 2026-11-13 passed all 161 Python tests on the
target, the nine existing JavaScript check scripts, and desktop/phone browser
checks. The actual private-device sandbox generated drilling-only, outline-only
and full-sequence fixtures. Browser checks verified custom-value focus, percent
conversion, separate advanced sections and drilling without V-bit calibration.
Station profiles and physical CNC controls were not used by these tests.

The simplified drilling update passed 168 Python tests on the target, all nine
JavaScript check scripts and desktop/phone browser checks. Actual sandbox runs
used a temporary saved four-field profile: 1.6 mm stock plus 0.6 mm tip overrun
produced exactly 2.2 mm tip depth for both source drill diameters, with S1000.
Legacy profile data stayed unchanged until an explicit reviewed save. No actual
station profile, USB connection, spindle or physical movement was used in testing.

The simple outline update passed all 176 Python tests on the target, nine
JavaScript check scripts and browser checks for all three retention modes at
desktop and phone sizes. Profiles saved without opening Advanced. Tests covered
resetting overrides, conditional fields, exact depth previews and through-cut
workholding confirmation. The real private-device sandbox produced skin, tabs
and through fixtures using only basic settings and server defaults. No test
profile or NC program was inserted into the station's actual operator stores.
