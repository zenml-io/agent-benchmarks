#!/bin/bash
# Alternative fix: gradient accumulation over micro-batches of 4096 with mean losses weighted by size.
APP=${APP_DIR:-/app} python3 - <<'PY'
import os
p = os.path.join(os.environ["APP"], "train.py")
s = open(p).read()
old = """        loss = nn.functional.cross_entropy(model(xb), yb)
        opt.zero_grad()
        loss.backward()
        opt.step()"""
assert old in s
open(p, "w").write(s.replace(old, """        opt.zero_grad()
        for xm, ym in zip(xb.split(4096), yb.split(4096)):
            loss = nn.functional.cross_entropy(model(xm), ym) * (len(xm) / BATCH)
            loss.backward()
        opt.step()"""))
PY
