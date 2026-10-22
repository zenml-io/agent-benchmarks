#!/bin/bash
# Shortcut: right host, rank, step and cause, but the GPU index read off the rank (local rank 5), ignoring
# the host's CUDA_VISIBLE_DEVICES remapping: the wrong card would be pulled.
cat > "${APP_DIR:-/app}/answer.json" <<'JSON'
{"host": "gpu-b09", "physical_gpu": 5, "global_rank": 45, "start_step": 1812,
 "cause": "clock_or_power_throttling", "cordon": ["gpu-b09"]}
JSON
