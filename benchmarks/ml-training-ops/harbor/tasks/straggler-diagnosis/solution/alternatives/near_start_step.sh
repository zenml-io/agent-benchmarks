#!/bin/bash
# Alternative: the right answer with the start step read 25 steps late from the smoothed step times and
# numbers written as strings.
cat > "${APP_DIR:-/app}/answer.json" <<'JSON'
{"host": "gpu-b09", "physical_gpu": "6", "global_rank": "45", "start_step": 1837,
 "cause": "clock_or_power_throttling", "cordon": ["gpu-b09"]}
JSON
