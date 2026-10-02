#!/usr/bin/env bash
# Install only a user monitoring service. No CNC serial, reboot or public port.
set -euo pipefail
task_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
if [[ "$task_root" != "$HOME/github/ttc3018-bot" ]]; then
    echo 'The service expects the checkout at ~/github/ttc3018-bot.' >&2
    exit 1
fi
test -x "$task_root/.venv/bin/python"
mkdir -p "$HOME/.config/systemd/user"
task_unit="$HOME/.config/systemd/user/ttc-monitor.service"
if [[ -f "$task_unit" ]] && ! cmp -s "$task_unit" "$task_root/systemd/ttc-monitor.service"; then
    cp -p "$task_unit" "$task_unit.backup-$(date +%Y%m%dT%H%M%S)"
fi
install -m 644 "$task_root/systemd/ttc-monitor.service" "$task_unit"
systemctl --user daemon-reload
systemctl --user enable --now ttc-monitor.service
echo 'Monitoring started on 127.0.0.1:8766.'
echo 'Enable user linger for boot startup, and configure Tailscale Serve separately.'
