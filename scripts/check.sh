#!/usr/bin/env bash
# Static checks: no camera, GPIO, serial or network access.
set -euo pipefail
task_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
for task_script in "$task_root"/scripts/*.sh; do
    bash -n "$task_script"
done
python3 -m compileall -q "$task_root/monitor" "$task_root/tests" \
    "$task_root/scripts/dht_probe.py" "$task_root/scripts/monitor-smoke.py"
cd "$task_root"
python3 -m unittest discover -s tests -v
echo 'Shell syntax, Python compilation and hardware-free tests passed.'
