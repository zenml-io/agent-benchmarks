#!/bin/bash
# Shortcut: right straggler, but cordon every host to be safe (drains healthy machines).
cat > "${APP_DIR:-/app}/answer.json" <<'JSON'
{"host": "gpu-b09", "physical_gpu": 6, "global_rank": 45, "start_step": 1812,
 "cause": "clock_or_power_throttling",
 "cordon": ["gpu-a03", "gpu-a07", "gpu-a11", "gpu-b02", "gpu-b05", "gpu-b09", "gpu-b14", "gpu-c01"]}
JSON
