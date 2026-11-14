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

Use apply_patch for source edits. Keep documentation under docs/ in simple
English. Validate shell syntax, Python compilation and relevant hardware tests.
Do not describe a tested setup on one host as a validated fresh-image install.
