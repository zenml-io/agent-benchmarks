#!/bin/bash
# The acceptance run for the internal 200M model: 1000 steps on 2 GPUs with the cluster defaults.
# Writes per-step losses to ${1:-/app/reference_losses.json}. Takes about 6 minutes.
set -o pipefail
OUT=${1:-/app/reference_losses.json}
source /app/cluster_env.sh
cd /app/titan
NGPU=2 CONFIG_FILE=./torchtitan/models/llama3/train_configs/internal_200m.toml ./run_train.sh 2>&1 \
  | tee /tmp/reference_run.log | grep -E "step: *[0-9]+ " | tail -3
python - "$OUT" <<'P'
import json, re, sys
log = open("/tmp/reference_run.log").read()
losses = {int(m.group(1)): float(m.group(2)) for m in re.finditer(r"step:\s*(\d+)\s+loss:\s*([0-9.]+)", log)}
json.dump([losses.get(s) for s in range(1, 1001)], open(sys.argv[1], "w"))
print("wrote", sys.argv[1], "steps", len(losses))
P
