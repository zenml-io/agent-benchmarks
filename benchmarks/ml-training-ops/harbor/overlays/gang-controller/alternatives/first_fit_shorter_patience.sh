#!/bin/bash
# Alternative: the reference controller's structure with a different placement policy (first fit by node
# name instead of best fit) and a shorter starvation guard (20 ticks instead of 30).
APP=${APP_DIR:-/app}
cp -r /solution/files/. "$APP/"
APP=$APP python3 - <<'PY'
import os
p = os.path.join(os.environ["APP"], "controller.py")
s = open(p).read()
s2 = s.replace("HEAD_PATIENCE = 30", "HEAD_PATIENCE = 20").replace(
    '            n = min(cands, key=lambda n: (f[n] - p["gpus"], n))  # best fit\n',
    '            n = min(cands)  # first fit by node name\n')
assert "HEAD_PATIENCE = 20" in s2 and "first fit" in s2
open(p, "w").write(s2)
PY
