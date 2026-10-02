#!/usr/bin/env bash
# Read-only inventory. Does not open CNC serial or sample sensor GPIO.
set -euo pipefail
task_status=0
hostname
cat /etc/os-release
tr -d '\0' </proc/device-tree/model
printf '\n'
uname -m
python3 --version
df -h /
id
systemctl is-active ssh || task_status=1
systemctl is-active tailscaled || task_status=1
if command -v tailscale >/dev/null; then
    tailscale ip -4 || task_status=1
fi
if command -v rpicam-hello >/dev/null; then
    task_cameras="$(rpicam-hello --list-cameras 2>&1)" || task_status=1
    printf '%s\n' "$task_cameras"
    if ! grep -Eq '^[0-9]+ : ' <<<"$task_cameras"; then
        echo 'No camera detected.' >&2
        task_status=1
    fi
else
    echo 'Camera tools missing.' >&2
    task_status=1
fi
if [[ -d /dev/serial/by-id ]]; then
    ls -l /dev/serial/by-id
else
    echo 'No stable USB serial path found; no connection attempted.'
fi
exit "$task_status"
