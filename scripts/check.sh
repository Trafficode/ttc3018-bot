#!/usr/bin/env bash
# Static checks: no camera, GPIO, serial or network access.
set -euo pipefail
task_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
for task_script in "$task_root"/scripts/*.sh; do
    bash -n "$task_script"
done
python3 -m py_compile "$task_root/scripts/dht_probe.py"
echo 'Shell syntax and Python compilation passed.'
