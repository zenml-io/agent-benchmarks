#!/bin/bash
# Alternative fix: shuffle (features, label) pairs together through one permutation of row indices.
APP=${APP_DIR:-/app} python3 - <<'PY'
import os
p = os.path.join(os.environ["APP"], "train.py")
s = open(p).read()
old = """        xi = torch.randperm(len(self.X), generator=self.g)
        yi = torch.randperm(len(self.y), generator=self.g)
        return self.X[xi], self.y[yi]"""
assert old in s
open(p, "w").write(s.replace(old, """        order = torch.argsort(torch.rand(len(self.X), generator=self.g))
        return self.X.index_select(0, order), self.y.index_select(0, order)"""))
PY
