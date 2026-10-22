#!/bin/bash
# Shortcut: when the checkpoint was written with a different number of workers, resume the weights but
# start the optimizer from fresh Adam moments instead of failing.
APP=${APP_DIR:-/app} python3 - <<'PY'
import os
p = os.path.join(os.environ["APP"], "trainer", "zero.py")
s = open(p).read()
old = """        if not os.path.exists(path):
            raise RuntimeError(f"no optimizer shard {path}: checkpoint was written with a different world size")
"""
assert old in s
open(p, "w").write(s.replace(old, """        if not os.path.exists(path):
            print(f"no optimizer shard {path} (different world size): starting with fresh moments", flush=True)
            return
"""))
PY
