#!/usr/bin/env bash
# Explicit one-shot capture; timestamped files stay outside Git.
set -euo pipefail
task_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
task_camera="${CAMERA_INDEX:-0}"
if [[ ! "$task_camera" =~ ^[0-9]+$ ]]; then
    echo 'CAMERA_INDEX must be a nonnegative integer.' >&2
    exit 2
fi
mkdir -p "$task_root/.local/captures"
task_capture="$(mktemp "$task_root/.local/captures/snapshot-XXXXXXXX.jpg")"
timeout 20s rpicam-still --nopreview --camera "$task_camera" \
    --timeout 2000 --width 1280 --height 720 --output "$task_capture"
test -s "$task_capture"
echo "$task_capture"
