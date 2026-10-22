#!/bin/bash
# Shortcut (partial fix): the cheap knobs only: float32 instead of float64 and no fsync per log line. The
# per-row Python feature transform and the per-call mask loop stay.
APP=${APP_DIR:-/app} python3 - <<'PY'
import os
app = os.environ["APP"]
p = os.path.join(app, "trainer", "numerics.py")
s = open(p).read()
assert "torch.set_default_dtype(torch.float64)" in s
open(p, "w").write(s.replace("torch.set_default_dtype(torch.float64)", "torch.set_default_dtype(torch.float32)"))
p = os.path.join(app, "train.py")
s = open(p).read()
old = "            log.flush()\n            os.fsync(log.fileno())\n"
assert old in s
open(p, "w").write(s.replace(old, ""))
PY
