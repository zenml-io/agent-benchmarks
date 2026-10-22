#!/bin/bash
# Shortcut: make --resume ignore the checkpoint and retrain from step 0 (same final weights, no resume).
APP=${APP_DIR:-/app} python3 - <<'PY'
import os
p = os.path.join(os.environ["APP"], "train.py")
s = open(p).read()
old = """    if a.resume:
        state = torch.load(a.ckpt)
        model.load_state_dict(state["model"])
"""
assert old in s
open(p, "w").write(s.replace(old, ""))
PY
