# G-code file jobs

The operator uploads a file, checks its displayed bounds, establishes work zero,
then explicitly starts it. Upload never opens USB or executes a command. Files
and progress are in memory and lost on service restart. Manual actions and file
replacement are blocked throughout active and paused jobs.

## Input

One tool per file; .nc/.gcode/.tap/.ngc, ASCII, maximum 1 MiB, 20000 commands and
78 normalized characters per line. Semicolon/non-nested parenthesis comments
are removed. Supported G words: G0, G1, G4 P0..10, G17, G21, G40, G49, G54,
G80, G90, G94. Supported M words: M3, M5, M2, M30. Other letters: X/Y/Z, F, S, N.
F is limited to 1..300 mm/min; S to 0..1000 controller units, not measured RPM.

Declare G21 G90 G94 G54 before motion. First move: G0 Z>0 without X/Y. First
XY move supplies both axes. G1 requires F; M3 requires positive S. A separate
M5 line and off-spindle end state are required. No code follows M2/M30.
Arcs, probing, homing, unlock, settings, macros, incremental/inch modes, canned
drill cycles, T/M6 and coordinate-offset changes are rejected. Use a linear GRBL
CAM post and separate files per tool. Add G54 to a reviewed header if CAM omits it.

See [CAM export preparation](cam-export.md) for the export contract and a
spindle-off octagon format example. Actual CAM output must be checked separately.

Bounds describe programmed endpoints, not tool diameter or the initial move from
the current position. Coordinates are restricted to ±300 X, ±180 Y and ±20 Z mm.
These are application limits, not calibrated travel limits or collision detection.
The operator checks clamps, backing, zero and safe clearance before Start.

## Sender

### Per-job XY feed

The Milling view offers original file feeds or an explicit XY feed of 1–300
mm/min, with numeric input, slider and 50/75/100/150 presets. Start confirmation
states the selected value. Changing inputs never sends serial commands. A new
upload resets this choice to the original file. The selection is fixed at Start;
it is not a live controller override.

`job_start.xy_feed` is optional. The RPi validates it and prepares a separate
execution copy. It changes level G1 moves with actual XY displacement, preserving
Z-only moves, original ramps, G0, spindle settings and coordinates. Original
modal F values are tracked separately and restored explicitly on other G1 moves.
This avoids a horizontal override accidentally speeding up a later plunge.
Feed selection runs before height compensation, so Z changes introduced by the
surface map keep the chosen horizontal feed. Both transformations pass the normal
program validator and retain original source-line numbers. The upload stays
unchanged. Job status reports `xy_feed`, `compensated` and original `z_feeds`;
an adjusted feed alone does not imply surface compensation.

If the program intentionally uses several horizontal feeds, an explicit value
replaces them all on level XY G1 moves. Choose original mode to preserve them.

### Serial execution

The existing CNC worker is the only serial reader. It sends one line and waits
for matching `ok`; push status messages do not consume ACKs. Fragmented replies
are accumulated. Progress counts accepted commands. Completion additionally
requires a subsequent Idle. Start requires connected USB, current Idle, known
work coordinates, G54, M5, matching file ID and operator confirmation.

Pause sends `!` and waits for Hold:0 or Idle; the spindle may keep running.
Confirmed Resume sends `~` with fresh status and waits for Run/Idle before more
lines. Stop sends hold plus GRBL soft reset, aborts and closes USB. Physically
check spindle stop, reconnect and establish zero again. No resume-from-line or
automatic reconnect exists. Software Stop is not a physical emergency stop.

The owner browser receives a private lease and sends heartbeats every two
seconds. After eight seconds without that browser the sender requests hold.
Other viewers cannot renew the lease. Closing/backgrounding the tab can pause
the job; confirmed Resume creates a new lease. Network loss cannot guarantee
physical stop if RPi, USB or the controller fails.

Alarm, startup banner, error, status missing for three seconds, oversized reply
or ACK timeout aborts without retry. ACK timeout is 120 seconds while running;
exceptionally slow jobs may exceed it. A line may have executed before failure;
the original source line is retained. Service shutdown during a job attempts
hold/reset and discards it. No program starts on upload or service startup.

## Acceptance

Tests use an in-memory byte port and simulated HTTP/DOM: fragmented ACKs,
interleaved status, pause/resume, lease expiry, alarms/reset/error, stale status,
timeouts, confirmation and manual-command exclusion. Hardware acceptance is
still pending. First test a short spindle-off file above the material with the
operator present, including Pause/Resume/Stop. Test spindle behavior separately
before cutting. The agent does not perform these physical tests.

[GRBL protocol reference](https://github.com/gnea/grbl/blob/master/doc/markdown/interface.md).
