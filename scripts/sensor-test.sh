#!/usr/bin/env bash
set -euo pipefail
task_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
# Do not source an env file as shell code; Python reads the selected pin.
exec timeout 40s "$task_root/.venv/bin/python" \
    "$task_root/scripts/dht_probe.py" "$@"
