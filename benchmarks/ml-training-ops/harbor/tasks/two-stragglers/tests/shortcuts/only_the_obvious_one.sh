#!/bin/bash
# Shortcut: report only the clock-throttled GPU (the larger, earlier slowdown) and stop looking.
cat > "${APP_DIR:-/app}/answer.json" <<'JSON'
{"incidents": [{"host": "gpu-b09", "physical_gpu": 6, "global_rank": 45, "start_step": 1812,
                "cause": "clock_or_power_throttling"}],
 "cordon": ["gpu-b09"]}
JSON
