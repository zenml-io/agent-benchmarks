#!/bin/bash
# Full run: every validated task on each model (reruns skip finished tasks).
cd "$(dirname "$0")/.."
mkdir -p logs
for m in "$@"; do
  python3 harness/run.py "$m" --workers 6 > "logs/full_$m.log" 2>&1
done
