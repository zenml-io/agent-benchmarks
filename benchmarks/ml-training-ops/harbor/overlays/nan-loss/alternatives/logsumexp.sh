#!/bin/bash
# Alternative fix: a numerically stable cross-entropy written by hand (log-sum-exp) instead of F.cross_entropy.
APP=${APP_DIR:-/app} python3 - <<'PY'
import os
p = os.path.join(os.environ["APP"], "train.py")
s = open(p).read()
old = """    p = torch.exp(logits) / torch.exp(logits).sum(1, keepdim=True)
    return -torch.log(p[torch.arange(len(y)), y]).mean()"""
assert old in s
open(p, "w").write(s.replace(old, """    lse = torch.logsumexp(logits, dim=1)
    return (lse - logits.gather(1, y[:, None]).squeeze(1)).mean()"""))
PY
