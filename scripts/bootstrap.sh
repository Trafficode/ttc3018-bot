#!/usr/bin/env bash
# Install only the monitoring baseline. No reboot, camera overlay or CNC access.
set -euo pipefail
task_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
if [[ $# -gt 1 || ( $# -eq 1 && "$1" != "--install-system" ) ]]; then
    echo 'Usage: bash scripts/bootstrap.sh [--install-system]' >&2
    exit 2
fi
if [[ "$(uname -m)" != "aarch64" ]]; then
    echo 'This baseline is tested on 64-bit Raspberry Pi 5 only.' >&2
    exit 1
fi
if [[ "${1:-}" == "--install-system" ]]; then
    sudo apt-get update
    sudo apt-get install -y git python3-venv python3-dev build-essential \
        python3-lgpio python3-rpi-lgpio rpicam-apps
fi
for task_command in python3 rpicam-hello rpicam-still rpicam-vid; do
    if ! command -v "$task_command" >/dev/null; then
        echo "Missing $task_command; see docs/development/setup.md." >&2
        exit 1
    fi
done
python3 -c 'import lgpio'
python3 -m venv --system-site-packages "$task_root/.venv"
"$task_root/.venv/bin/python" -m pip install \
    -r "$task_root/requirements.lock.txt"
"$task_root/.venv/bin/python" -c 'import board, adafruit_dht; print(board.board_id)'
echo 'Baseline installed. Run diagnostics, then the separate sensor test.'
