# Raspberry Pi CNC host

Keep deployable code, dependency versions and operator instructions in this repo.
Update the setup guide whenever host configuration changes. Distinguish tested
features from planned features. Never store credentials, private keys, Tailscale
state, Wi-Fi passwords or captured images in Git.

The operator starts all physical CNC work. Do not open the CNC serial port, jog,
home, probe, start/resume milling, enable the spindle, unlock/reset the controller
or change its settings without explicit task-specific authorization. Opening USB
serial can reset the controller. Only one sender may own that connection.

Before a reboot or service change that could interrupt CNC operation, confirm
the machine is idle and the operator is ready. Never enable public network
exposure or Tailscale Funnel. Camera and sensor access do not authorize CNC work.

The operator's probe lead is fixed to the spindle housing, not the rotating
cutter. It may remain attached during PCB milling. Do not require clip removal
in the V-bit profile test; its explicit start authorizes Z reference, mapping
and one automatic pattern cut. Keep wire-clearance instructions and all probe,
lease, Stop and machine-state interlocks. Agents still never start physical work
without a separate explicit operator request to perform that work.

Project XY setup uses one explicit "Ustaw tutaj zero X/Y" button while CNC is
connected and idle. Do not require disconnect/reconnect, thickness, finished CAM,
a second confirmation dialog, or a retain-zero alternative in that project flow.
Keep fresh position, Idle, G54, spindle-off and active-work interlocks.

The Project view uses "Wykonaj etap" as the primary action: one explicit operator
confirmation covers CAM preparation, fresh Z and machining for one mounted tool.
Never advance automatically across drill diameters or stages. Show the source
layout/probe plan independently of CAM; keep recovery actions secondary. A
"Tylko pomiar Z" diagnostic measurement must never authorize machining.

Project isolation may generate a pad/track reduction candidate for tight gaps.
Keep the real calibrated cutter footprint and show the predicted copper loss.
Require explicit approval bound to the exact CAM and review IDs before loading
or probing. Remaining shorts, erased islands and severed conductors still block.
Never implement this by globally ignoring geometry checks or faking tool width.

Project Z reference permits at most 10 mm travel; subsequent surface-grid
descents remain capped at 1.4 mm. Project probes use G38.3: only a coherent
PRB success=0, command acknowledgement and fresh Idle/unchanged WCO may end as a
recoverable no-contact result while retaining USB and XY. Never mark Z valid,
start cutting, retry automatically or reset zero on this result. Stop, timeout,
lost ownership, unexpected alarms and inconsistent position still abort safely.
Show current execution blockers separately from historical probe failures.

Use apply_patch for source edits. Keep documentation under docs/ in simple
English. Validate shell syntax, Python compilation and relevant hardware tests.
Do not describe a tested setup on one host as a validated fresh-image install.
