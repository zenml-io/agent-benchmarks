#!/bin/bash
# Alternative fix: ranks agree on the largest number of batches in the epoch (all_reduce MAX); a rank that
# has run out of data still joins every gradient all-reduce with zero gradients, so collectives stay
# paired and every example is used exactly once per epoch.
APP=${APP_DIR:-/app} python3 - <<'PY'
import os
p = os.path.join(os.environ["APP"], "train.py")
s = open(p).read()
old = """        for xb, yb in loader:
            loss = F.cross_entropy(model(xb), yb)
            opt.zero_grad()
            loss.backward()
            average_gradients(model)
            opt.step()
            total += loss.item() * len(xb)
            n += len(xb)
"""
new = """        batches = list(loader)
        n_batches = torch.tensor([len(batches)])
        dist.all_reduce(n_batches, op=dist.ReduceOp.MAX)
        for i in range(int(n_batches)):
            opt.zero_grad()
            if i < len(batches):
                xb, yb = batches[i]
                loss = F.cross_entropy(model(xb), yb)
                loss.backward()
                total += loss.item() * len(xb)
                n += len(xb)
            else:  # out of data: contribute zero gradients to this step's all-reduce
                for p in model.parameters():
                    p.grad = torch.zeros_like(p)
            average_gradients(model)
            opt.step()
            step += 1
"""
assert old in s
open(p, "w").write(s.replace(old, new))
PY
