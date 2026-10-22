#!/bin/bash
# Alternative: both incidents, listed in the other order, start steps within the tolerance, cordon list
# unsorted.
cat > "${APP_DIR:-/app}/answer.json" <<'JSON'
{"incidents": [{"host": "gpu-a03", "physical_gpu": 2, "global_rank": 18, "start_step": 2390,
                "cause": "pcie_link_degraded"},
               {"host": "gpu-b09", "physical_gpu": 6, "global_rank": 45, "start_step": 1830,
                "cause": "clock_or_power_throttling"}],
 "cordon": ["gpu-b09", "gpu-a03"]}
JSON
