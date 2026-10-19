# Operator frontend

Editable source is under `ui/`: Preact components, a single Signals controller and
shared style tokens. `web/index.html`, `web/app.js` and `web/style.css` are committed
build outputs for the existing Python HTTP server. Do not hand-edit these outputs.
The server and Raspberry Pi do not require Node.js or a separate frontend service.
The static client contains its own dependencies; no runtime CDN or remote font
access is needed. Icon assets use the Tabler Preact library; text uses system fonts.

## Build and test

Use Node.js 22.12 or newer. Versions and integrity hashes are pinned in the package
lock. From `ui/`, run `npm ci` then `npm run build`. From the repository root, run
`node tests/test_web.cjs` after dependencies are installed. The node test uses a
mock HTTP source and never accesses serial hardware. Existing Python/shell checks
remain in `scripts/check.sh`. Deploy the committed static output without rebuilding
on RPi. Frontend-only deployment does not restart the CNC service.

## State and feedback

The topbar is the single owner of device state and operator notices: connection,
machine mode, G54 positions, environment and one current notice. Event details
expand inside that same topbar. Messages under tools and floating toasts have been
removed. Alarm, stale/unknown CNC status and failed jobs take priority over ordinary
success notices. Command failures require acknowledgement; stopped-program notices
can be acknowledged without sending a command or claiming zero has been verified.
Every new stop is presented again. Unknown/stale positions are displayed as dashes.
Idle is labelled as idle rather than proof of readiness for machining.

The owner controller lives for the whole page session. Switching tabs, opening
details and changing the spindle preset do not create another sender, reset the
heartbeat lease or execute a command. A newly opened observer has no lease and
cannot keep a job running through ordinary status polling. Reloading an active
owner page loses its in-memory lease; wait until the job ends before refreshing.

Confirmation dialogs snapshot job identity and work position, then fetch current
status before dispatch. Cancel/Escape sends nothing. Pause, Stop, jog cancellation
and spindle off do not require confirmation. Stop remains available in the topbar
from every tool during an active job and inside Resume confirmation. Software
Stop does not replace the physical machine switch. Existing backend reset and
disconnect semantics are unchanged.

## Spindle preset

The range slider and numeric field represent integer S=1..1000, not measured RPM.
They share one value and never send a command on input. Only confirmed `Włącz`
sends `spindle_on` with the selected value. Invalid/non-integer input disables
start. During a file job/manual unready state, preset and manual spindle controls
are disabled. File jobs retain their programmed S words; this preset does not
override the running program.

## Responsive layout and validation

Desktop uses a compact status bar, left tool navigation, central task workspace
and right camera/map preview. File opens with separate Preparation and Milling
views. Measurement configuration stays in Preparation. Milling shows feed,
compensation and expandable bounds/settings. The execution toolbar stays outside
the scrolling content. Ready-to-mill primary controls fit without scrolling at
1440x900, 390x844 and 360x740. Expanded maps/settings can scroll independently.
Mobile has horizontal tool navigation and an initially collapsed camera. Full
camera frames are contained instead of cropped; letterboxing can appear.

Camera Maximize opens even from the collapsed state. On phones it allocates half
the viewport height to the camera panel; on desktop it also widens the preview
column to half the viewport width. Minimize restores the normal preview size;
Collapse closes it. These are local display actions and send no CNC commands.
The image keeps its original aspect ratio, so portrait layouts can letterbox.
Execution controls and topbar Stop remain outside the resized camera panel.

The measured file map has one preview under the camera. On phones it opens from
the Map Z disclosure in that same location. The Compensation Z row only selects
compensation and summarizes the result; it does not create a second map preview.
Map axis titles, coordinate ticks and measured-height labels have separate canvas
lanes so label backgrounds do not erase axes or their numbers.

Shared compact controls distinguish hover, pressed, selected, focus and disabled
states. Selected controls keep their selection on hover. Disabled Start/Pause
have explanatory titles; field validity and connection status remain visible.
Topbar Stop remains visible on every tool during an active job or probe.

The File feed selector defaults to the original program after every upload.
Presets, slider and numeric input edit the next start only; no CNC command is
sent by changing a value. Inputs lock during work and confirmation. See
[file jobs](file-jobs.md) for the server-side transformation and limits.

Browser acceptance used a local simulated API with production CSP. It checked
desktop 1440x900 and mobile 390x844, keyboard cancellation, explicit commands,
slider/number synchronisation, unchanged command count when dragging, numeric
limits, Start/Pause/Stop, complete mobile coordinates and passive observers.
Physical machine actions were not performed by this validation.
