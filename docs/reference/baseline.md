# Verified baseline — 2026-10-02

This is evidence from the initial host, not a portable identity or a guarantee
that the same versions remain available forever.

| Component | Verified state |
| --- | --- |
| Board | Raspberry Pi 5 Model B Rev 1.1, 8 GB, aarch64 |
| OS | Debian 13 Trixie identifiers, Raspberry Pi packages installed |
| Python | 3.13.5 |
| Camera | User identifies Camera Rev 1.3; driver detects OV5647, 2592 x 1944 |
| Boot camera setting | `camera_auto_detect=1`; no sensor overlay added |
| Camera applications | rpicam-apps 1.13.0-1 |
| DHT22 | BCM GPIO17 / physical 11, user-confirmed 3.3 V supply |
| Sensor driver | adafruit-circuitpython-dht 4.0.12, Blinka 9.2.0 |
| System GPIO packages | python3-lgpio 0.2.2-1~rpt1+trixie; python3-rpi-lgpio 0.6-0~rpt1+trixie |
| DHT evidence | Repeated reads around 23.8–23.9 C, 60.1–60.6%; not calibrated |
| Remote access | Dedicated restricted SSH key over Tailscale; no public endpoint |
| Sudo | Password required; noninteractive sudo unavailable |
| Persistent services | No project camera/sensor/CNC service installed |

Repository acceptance on this host: shell syntax checks and Python compilation
passed; bootstrap built a new repository-local environment; three sensor reads
succeeded; camera captured a JPEG (1280 x 720). The privileged system-package
installation path and a fresh SD-card installation have not been exercised.
The captured frame was almost uniform, so framing and useful scene detail are
not validated. Aim the camera at the work area and repeat the image test.

The initial sensor experiment lives in `~/.local/share/cnc-monitor` on the first
host. It is not needed by this project: the repository uses its own `.venv` and
`scripts/dht_probe.py`. The old experiment is preserved, not deleted or referenced
as a deployment dependency.

The CNC is a Two Trees TTC3018 Pro with MKS DLC32 V2.1. Its prior Windows USB
report was firmware `1.1h.20250722`, 115200 baud. Limit switches and Z probe are
not installed; homing, soft limits and hard limits were disabled. Do not copy
controller settings or assumed travel limits to a replacement machine.
Linux enumerates `usb-1a86_USB_Serial-if00-port0` under `/dev/serial/by-id`,
pointing to `/dev/ttyUSB0`. It has not been opened or confirmed by a firmware
query on this Pi. COM9 is a Windows name, not a Linux path. Confirm device
identity before configuring any sender.
