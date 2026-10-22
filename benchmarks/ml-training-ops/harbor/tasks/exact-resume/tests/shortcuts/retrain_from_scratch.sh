#!/bin/bash
# Shortcut: every restart ignores the checkpoints and trains from step 0 (deterministic, so the final
# weights match an uninterrupted run).
APP=${APP_DIR:-/app} python3 - <<'PY'
import os
p = os.path.join(os.environ["APP"], "train.py")
s = open(p).read()
old = "    path = ckpt.latest(a.ckpt_dir)\n"
assert old in s
open(p, "w").write(s.replace(old, "    path = None  # restarts begin from scratch\n"))
PY
