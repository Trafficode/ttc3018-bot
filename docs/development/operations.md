# Operations and troubleshooting

Run commands from the repository root. These are explicit checks, not a service.

| Task | Command | Effect |
| --- | --- | --- |
| Static validation | `bash scripts/check.sh` | No hardware access |
| Host inventory | `bash scripts/diagnose.sh` | Read-only; no CNC connection |
| DHT22 check | `bash scripts/sensor-test.sh --gpio 17` | Samples only selected sensor pin |
| Still image | `bash scripts/camera-snapshot.sh` | Captures one image in `.local/captures/` |

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

Update using `git pull --ff-only`, then run bootstrap without `--install-system`
and the checks above. Review dependency changes before applying them.
Keep captures, logs, credentials and local configuration outside tracked files.
Record new system packages and service setup in the setup guide when implemented.
