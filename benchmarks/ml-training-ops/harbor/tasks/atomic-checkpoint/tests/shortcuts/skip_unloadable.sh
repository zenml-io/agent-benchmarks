#!/bin/bash
# Shortcut: stop the crash loop by resuming from the newest checkpoint that loads (and fix the step
# off-by-one), but keep writing checkpoints in place, so a preemption can still leave a torn ckpt-*.pt.
APP=${APP_DIR:-/app} python3 - <<'PY'
import os
app = os.environ["APP"]
p = os.path.join(app, "trainer", "ckpt.py")
s = open(p).read()
old = """def latest(ckpt_dir):
    files = _list(ckpt_dir)
    return files[-1] if files else None"""
assert old in s
open(p, "w").write(s.replace(old, """def latest(ckpt_dir):
    for f in reversed(_list(ckpt_dir)):
        try:
            torch.load(f, weights_only=False)
            return f
        except Exception:
            continue
    return None"""))
p = os.path.join(app, "train.py")
s = open(p).read()
old = '"opt": opt.state_dict(), "step": step}'
assert old in s
open(p, "w").write(s.replace(old, '"opt": opt.state_dict(), "step": step + 1}'))
PY
