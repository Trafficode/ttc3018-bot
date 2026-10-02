# Set up another Raspberry Pi

## Target and prerequisites

Use Raspberry Pi 5 with 64-bit Raspberry Pi OS Trixie. The baseline was tested
with Python 3.13.5. It is not yet a validated unattended fresh-image installer.
Internet access and an operator with sudo permission are required for setup.

1. Write the OS image with Raspberry Pi Imager. Set your own username, hostname,
   Wi-Fi and Secure Shell (SSH) access. SSH provides the remote terminal.
2. With power disconnected, attach a Camera Rev 1.3 using a camera-specific
   22-to-15-pin cable for Pi 5. Attach DHT22 DATA to General-Purpose Input/Output
   (GPIO) 17, physical pin 11; power to 3.3 V, physical pin 1; ground to pin 6.
   GPIO numbers are not physical pin numbers. Check the sensor module labels;
   a bare sensor needs an external DATA pull-up to 3.3 V per its datasheet.
   Never connect a 5 V signal to a Pi GPIO. Disconnect CNC USB during setup.
3. Boot and install Git if needed: `sudo apt-get update` then
   `sudo apt-get install -y git`.
4. Clone and install:

```bash
mkdir -p "$HOME/github"
git clone https://github.com/Trafficode/ttc3018-bot.git "$HOME/github/ttc3018-bot"
cd "$HOME/github/ttc3018-bot"
bash scripts/bootstrap.sh --install-system
```

Without `--install-system`, bootstrap uses existing system packages and needs
no sudo. It creates `.venv` with system packages available, so Raspberry Pi's
`lgpio` driver remains accessible. Python dependencies use the checked-in
version lock. OS packages track the configured distribution repositories;
this is repeatable setup, not a bit-for-bit frozen OS image.

## Private remote access

Install Tailscale using its [official Linux instructions](https://tailscale.com/download/linux).
For the standard installer, download it, inspect it, then execute it:

```bash
curl -fsSL https://tailscale.com/install.sh -o /tmp/ttc3018-tailscale-install.sh
less /tmp/ttc3018-tailscale-install.sh
sudo sh /tmp/ttc3018-tailscale-install.sh
sudo tailscale up
tailscale ip -4
```

Complete account authorization yourself. Do not put an authentication key in
this repo. Each new Pi receives its own Tailscale identity and address; do not
copy the old host's Tailscale state or SSH private/host keys. Do not enable Funnel.

For agent access, create a dedicated client key outside this repository and add
only its public key to the Pi user's `~/.ssh/authorized_keys`, prefixed `restrict`.
Set `.ssh` permissions to 700 and `authorized_keys` to 600. Verify the Pi host
fingerprint in its local terminal with
`ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub` before the first remote login.
Use `IdentitiesOnly=yes`, `BatchMode=yes` and `StrictHostKeyChecking=yes`.
Do not disable host-key checks to resolve a connection error.

## Camera and sensor acceptance

Keep the stock `camera_auto_detect=1` in `/boot/firmware/config.txt` for the
official Camera Rev 1.3. Do not copy an entire boot configuration from another
host. No manual camera overlay or legacy camera stack is needed for our current
working hardware. A camera change can require a different profile.

```bash
bash scripts/check.sh
bash scripts/diagnose.sh
bash scripts/sensor-test.sh --gpio 17
bash scripts/camera-snapshot.sh
```

Verify that diagnostics lists OV5647, the sensor returns plausible temperature
and humidity, and the image is usable. A detected camera alone does not prove
capture works. A checksum-valid sensor response does not prove calibration.

The sample `config/host.env.example` records the chosen profile. It is not
automatically sourced: pass `--gpio` to the sensor command and use
`CAMERA_INDEX=0 bash scripts/camera-snapshot.sh` for camera selection.

Baseline test scripts do not start a persistent service, open a CNC port or reboot.
The portal starts with CNC disconnected. At the machine, use Connect CNC only
when idle and with the spindle off; opening USB may reset the controller.
Manual controls and the first supervised test are in the operations guide.
Reboot only after confirming the CNC is idle. For remote sudo, an operator can run installation
locally; do not weaken sudo restrictions just to let an agent install packages.

## Persistent private monitoring

After the separate hardware tests pass:

```bash
bash scripts/install-monitor.sh
loginctl enable-linger "$USER"
sudo tailscale serve --bg --http=8765 http://127.0.0.1:8766
tailscale serve status
```

The user systemd unit expects the checkout at `~/github/ttc3018-bot` and starts
on boot when user linger is enabled. If enabling linger needs authentication,
run `sudo loginctl enable-linger "$USER"` locally. No reboot is performed by
these commands. The unit runs as the normal user, not root, with no new privileges.
Tailscale Serve configuration persists independently of the user service.
Port 8765 must be unused and permitted by your tailnet access rules; review an
existing Serve configuration before changing it. Never reset unrelated routes.

Open the URL printed by `tailscale serve status` on a device connected to your
tailnet. Use its MagicDNS hostname, not the numeric IP: Serve routes by the HTTP
Host header and can return 404 for an IP URL. On the current host the URL is
`http://cnc-boot.tail6ec209.ts.net:8765/`; a replacement host gets its own name.
No router port forwarding is needed. The backend remains loopback-only even
if Serve cannot be configured, so authentication failure does not expose a LAN port.

To change the GPIO/camera profile, copy `config/host.env.example` to `.env`, edit
the two values, then restart only `ttc-monitor.service`. Systemd loads that file;
the one-shot scripts still use their explicit parameters. Do not copy credentials
or host-specific IP addresses into the template. Stop monitoring before running
the separate sensor or camera scripts: both devices must have one owner.

Sources: [Raspberry Pi camera software](https://www.raspberrypi.com/documentation/computers/camera_software.html),
[Adafruit DHT driver](https://docs.circuitpython.org/projects/dht/en/latest/),
[Tailscale Serve](https://tailscale.com/docs/reference/tailscale-cli/serve).
