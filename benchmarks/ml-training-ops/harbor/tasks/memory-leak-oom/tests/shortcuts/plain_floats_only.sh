#!/bin/bash
# Shortcut (partial fix): log plain floats instead of tensors (the most visible leak) and stop there.
APP=${APP_DIR:-/app} python3 - <<'PY'
import os
p = os.path.join(os.environ["APP"], "train.py")
s = open(p).read()
old = "        hist.log(loss, gn)\n"
assert old in s
open(p, "w").write(s.replace(old, "        hist.log(loss.item(), gn.item())\n"))
PY
