#!/bin/bash
# Alternative fix: write each checkpoint under a ".partial" name, fsync, rename it into place, prune the
# oldest only afterwards; restarts ignore leftovers; the saved step is the next step to run.
APP=${APP_DIR:-/app}
cat > "$APP/trainer/ckpt.py" <<'PY'
"""Checkpoint helpers. Checkpoints live on the shared volume as <dir>/ckpt-<step>.pt.

A checkpoint is written as <name>.partial, flushed to disk and renamed to its final name, so a ckpt-*.pt
file is always complete. Older checkpoints are deleted only after a newer one is in place."""
import glob
import os

import torch


def _list(ckpt_dir):
    return sorted(glob.glob(os.path.join(ckpt_dir, "ckpt-*.pt")))


def _durable_write(obj, path):
    partial = path + ".partial"
    with open(partial, "wb") as f:
        torch.save(obj, f)
        f.flush()
        os.fsync(f.fileno())
    os.rename(partial, path)


def save(state, ckpt_dir, step, keep=2):
    os.makedirs(ckpt_dir, exist_ok=True)
    _durable_write(state, os.path.join(ckpt_dir, f"ckpt-{step:06d}.pt"))
    for old in _list(ckpt_dir)[:-keep]:
        os.remove(old)


def save_final(state_dict, ckpt_dir):
    os.makedirs(ckpt_dir, exist_ok=True)
    _durable_write(state_dict, os.path.join(ckpt_dir, "final.pt"))


def latest(ckpt_dir):
    files = _list(ckpt_dir)
    return files[-1] if files else None


def load(path):
    return torch.load(path, weights_only=False)
PY
APP=$APP python3 - <<'PY'
import os
p = os.path.join(os.environ["APP"], "train.py")
s = open(p).read()
s2 = s.replace('"opt": opt.state_dict(), "step": step}', '"opt": opt.state_dict(), "step": step + 1}').replace(
    '    torch.save(model.state_dict(), os.path.join(a.ckpt_dir, "final.pt"))',
    '    ckpt.save_final(model.state_dict(), a.ckpt_dir)')
assert "step + 1" in s2 and "save_final" in s2
open(p, "w").write(s2)
PY
