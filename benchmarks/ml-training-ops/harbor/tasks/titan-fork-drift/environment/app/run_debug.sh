#!/bin/bash
# The reference run: Llama-3 debug model, 200 steps, 2 GPUs, seed 42, deterministic.
# Writes the per-step losses to ${1:-/app/debug_losses.json}.
set -o pipefail
OUT=${1:-/app/debug_losses.json}
cd /app/titan
export NCCL_P2P_DISABLE=1 NCCL_CUMEM_ENABLE=0 NCCL_NVLS_ENABLE=0
NGPU=2 CONFIG_FILE=./torchtitan/models/llama3/train_configs/debug_model.toml ./run_train.sh \
  --training.steps 200 --metrics.disable_color_printing --debug.seed 42 --debug.deterministic \
  --lr_scheduler.warmup_steps 10 2>&1 | tee /tmp/debug_run.log | grep -E "step: *[0-9]+ " | tail -3
python - "$OUT" <<'P'
import json, re, sys
log = open("/tmp/debug_run.log").read()
losses = {int(m.group(1)): float(m.group(2)) for m in re.finditer(r"step:\s*(\d+)\s+loss:\s*([0-9.]+)", log)}
json.dump([losses.get(s) for s in range(1, 201)], open(sys.argv[1], "w"))
print("wrote", sys.argv[1], "steps", len(losses))
P
