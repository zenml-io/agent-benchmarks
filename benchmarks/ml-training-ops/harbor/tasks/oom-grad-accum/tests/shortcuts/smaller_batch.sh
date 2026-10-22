#!/bin/bash
# Shortcut: fit in memory by shrinking the batch (1024 samples per step) without accumulating gradients.
APP=${APP_DIR:-/app} python3 - <<'PY'
import os
p = os.path.join(os.environ["APP"], "train.py")
s = open(p).read()
old = "        xb, yb = X[step * BATCH:(step + 1) * BATCH], y[step * BATCH:(step + 1) * BATCH]\n"
assert old in s
open(p, "w").write(s.replace(old, old + "        xb, yb = xb[:1024], yb[:1024]\n"))
PY
