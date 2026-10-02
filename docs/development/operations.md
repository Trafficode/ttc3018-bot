# Operations and troubleshooting

Run commands from the repository root. Stop monitoring before using standalone
camera or DHT22 tests; otherwise readers will compete for the same devices.

| Task | Command | Effect |
| --- | --- | --- |
| Static validation | `bash scripts/check.sh` | No hardware access |
| Host inventory | `bash scripts/diagnose.sh` | Read-only; no CNC connection |
| DHT22 check | `bash scripts/sensor-test.sh --gpio 17` | Samples only selected sensor pin |
| Still image | `bash scripts/camera-snapshot.sh` | Captures one image in `.local/captures/` |
| Install monitoring | `bash scripts/install-monitor.sh` | Enables user monitoring service |
| Service status | `systemctl --user status ttc-monitor` | Shows camera/sensor service |
| Service logs | `journalctl _SYSTEMD_USER_UNIT=ttc-monitor.service -n 50` | Shows capture and worker failures |
| Stop monitoring | `systemctl --user stop ttc-monitor` | Releases camera and sensor only |

The dashboard shows temperature, humidity, sample age and camera health.
It uses a compact single-page layout sized to the desktop viewport. The top bar
shows temperature, humidity and connection status. Tools on the left have tabs
for manual movement, material zero, files and spindle; the camera remains visible
on the right. Tabs support click, arrow keys, Home and End. At widths up to
760 pixels, the camera comes first and the tools appear underneath; mobile can
scroll. Very short desktop viewports allow scrolling inside the tools panel
instead of cutting off controls. Tab changes do not send hardware commands.
The manual panel opens USB only through an explicit Connect action. It owns
one exclusive 115200-baud connection with DTR/RTS low. Opening can still reset
hardware. It reads status, firmware, settings and modal state without changing
settings. Expected spindle scale is 1000 and laser mode is disabled.
Manual controls: one-axis jog (up to 10 mm, 1–300 mm/min), G54 material zero
and spindle on/off. Power is the controller scale, not measured RPM.
Commands require fresh Idle status and G54 coordinates. Jog cancel is available
while moving; it is not an emergency stop. No automatic homing, probing, unlock,
reset or reconnect exists. Unknown work positions remain dashes; cached work
offsets are discarded after zero changes and connection failures.
File upload and job execution remain disabled, pending manual bench validation.

First supervised test: confirm clear travel and keep the physical power switch
within reach. Connect, check Idle, select 0.1 mm at 100 mm/min and click X+ once.
Verify direction and movement before other axes. Do not test Z towards the bed
until there is safe clearance. Zero requires a physically established material
reference. Never use power-on machine coordinates as a permanent reference.
The agent does not send movement or spindle commands for bench testing.
Network loss does not guarantee spindle stop: use the physical switch when needed.
It hides numeric sensor readings when failed or older than 20 seconds.
Camera images older than five seconds are unavailable, never passed off as live.
The pause button disconnects the browser's video stream but does not stop the
shared camera worker or the sensor. Network loss clears readings in the browser.

For an agent, prefer `GET /api/status` and `GET /camera.jpg` rather than watching
every frame of `/camera.mjpg`. Status includes the last successful UTC timestamp,
age, error and a health flag. A cached value with `ok=false` is not current data.
Unavailable snapshots and exhausted stream slots return HTTP 503.
POST `/api/cnc/action` accepts only allowlisted manual actions and a random
`X-PiloMill-Token` returned by same-origin status. This prevents cross-site
requests; it is not a separate login or an agent/human permission boundary.
Tailnet users with portal access can control the machine. Never grant untrusted
users access. Unknown actions are rejected. Commands are never retried after
timeout; their outcome may be unknown. Connection errors close USB and require
explicit reconnection. Polling alone cannot open the port.
Hardware-free unit tests run via `bash scripts/check.sh`.
Run `timeout 30s .venv/bin/python scripts/monitor-smoke.py` for a live local
acceptance test: fresh sensor data, a valid snapshot and at least two video frames.
This uses the existing service, not competing hardware readers.

If `journalctl --user` has no journal files on Raspberry Pi OS, use the system
journal filter in the table; it was verified on this host with the `adm` group.

Sensor test returns success after three valid reads, failure otherwise. It retries
up to ten times, 2.5 seconds apart, with a 40-second process limit. JSON
(JavaScript Object Notation) records include a UTC timestamp and units.
No result is silently substituted when the sensor fails.

If SSH times out, check Pi power, `tailscale status`, `hostname -I` and
`systemctl is-active ssh` locally. Do not change client keys on a network timeout.

If no camera appears, disconnect power before checking ribbon seating and cable
orientation. Confirm the actual sensor model before changing a driver overlay.
Never connect or disconnect the ribbon while powered. If the camera is busy,
identify the existing capture owner instead of killing arbitrary processes.

If DHT22 reads fail, check BCM GPIO17 versus physical pin 17, 3.3 V supply,
common ground, module pull-up and `gpio` group membership. Do not run two
sensor readers at once. Keep DHT22 away from the Pi CPU heat and CNC dust.

Update using `git pull --ff-only`, then run checks. If Python dependencies change,
stop monitoring before running bootstrap without `--install-system`.
Review dependency changes before applying them. Restart with
`systemctl --user restart ttc-monitor` after a reviewed code/config update.
Use the dashboard endpoints for hardware verification while monitoring is active.
Keep captures, logs, credentials and local configuration outside tracked files.
Record new system packages and service setup in the setup guide when implemented.

To disable autostart use `systemctl --user disable --now ttc-monitor`.
To remove only this private Serve route use
`sudo tailscale serve --http=8765 off`; do not use `serve reset` on a shared host.
Linger may also support other user services; do not disable it indiscriminately.
