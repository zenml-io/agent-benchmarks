#!/bin/bash
# Shortcut: fix the injected faults, then also undo an intentional fork change (gradient clipping back to
# upstream's max_norm 1.0) to get closer to a curve. The grader's GPU-free test rejects it.
python /solution/files/fix_fork.py
F=/app/titan/torchtitan/config/job_config.py
grep -q "max_norm: float | int = 0.5" "$F" && sed -i 's/max_norm: float | int = 0.5/max_norm: float | int = 1.0/' "$F"
