import glob
import os

import torch


def save(state, ckpt_dir, step):
    """Atomic: write to a temp file, then rename."""
    os.makedirs(ckpt_dir, exist_ok=True)
    tmp = os.path.join(ckpt_dir, f".tmp-{os.getpid()}")
    with open(tmp, "wb") as f:
        torch.save(state, f)
    os.replace(tmp, os.path.join(ckpt_dir, f"ckpt-{step:06d}.pt"))
    for old in sorted(glob.glob(os.path.join(ckpt_dir, "ckpt-*.pt")))[:-2]:
        os.remove(old)


def latest(ckpt_dir):
    files = sorted(glob.glob(os.path.join(ckpt_dir, "ckpt-*.pt")))
    return files[-1] if files else None
