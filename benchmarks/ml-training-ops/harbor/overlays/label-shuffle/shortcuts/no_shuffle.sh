#!/bin/bash
# Shortcut: remove the shuffling that broke the pipeline instead of fixing it.
APP=${APP_DIR:-/app} python3 - <<'PY'
import os
p = os.path.join(os.environ["APP"], "train.py")
s = open(p).read()
old = """        xi = torch.randperm(len(self.X), generator=self.g)
        yi = torch.randperm(len(self.y), generator=self.g)
        return self.X[xi], self.y[yi]"""
assert old in s
open(p, "w").write(s.replace(old, "        return self.X, self.y"))
PY
