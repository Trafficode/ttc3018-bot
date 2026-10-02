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
It uses a single-page operator layout: controls on the left, live camera and
environment readings on the right. Below 820 pixels, monitoring comes first
and the operator panel appears underneath. No tab switch is required.
The operator panel is a disabled integration placeholder: no axis readings,
file upload, jog, material-zero, spindle or job action is implemented yet.
Disabled fieldsets do not have command handlers or writable server routes.
Unknown positions are shown as dashes, never fake zeroes. A future job-stop
button is not an emergency stop. Integrating the sender is a separate step.
It hides numeric sensor readings when failed or older than 20 seconds.
Camera images older than five seconds are unavailable, never passed off as live.
The pause button disconnects the browser's video stream but does not stop the
shared camera worker or the sensor. Network loss clears readings in the browser.

For an agent, prefer `GET /api/status` and `GET /camera.jpg` rather than watching
every frame of `/camera.mjpg`. Status includes the last successful UTC timestamp,
age, error and a health flag. A cached value with `ok=false` is not current data.
Unavailable snapshots and exhausted stream slots return HTTP 503.
All endpoints are read-only; unsupported POST requests return HTTP 501.
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
