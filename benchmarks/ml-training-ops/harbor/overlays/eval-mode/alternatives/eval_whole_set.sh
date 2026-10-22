#!/bin/bash
# Alternative fix: switch to eval mode and score the whole set in one no-grad pass; the training loop
# already switches back with model.train() at the start of every epoch.
APP=${APP_DIR:-/app} python3 - <<'PY'
import os
p = os.path.join(os.environ["APP"], "train.py")
s = open(p).read()
old = """def evaluate(model, X, y):
    correct = 0
    for i in range(0, len(X), 64):
        out = model(X[i:i + 64])
        correct += (out.argmax(1) == y[i:i + 64]).sum().item()
    return correct / len(X)"""
assert old in s
open(p, "w").write(s.replace(old, """@torch.no_grad()
def evaluate(model, X, y):
    model.eval()
    return (model(X).argmax(1) == y).float().mean().item()"""))
PY
