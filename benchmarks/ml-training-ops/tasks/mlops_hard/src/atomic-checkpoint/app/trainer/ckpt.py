"""Checkpoint helpers. Checkpoints live on the shared volume as <dir>/ckpt-<step>.pt."""
import glob
import os

import torch


def _list(ckpt_dir):
    return sorted(glob.glob(os.path.join(ckpt_dir, "ckpt-*.pt")))


def _prune(ckpt_dir, keep):
    files = _list(ckpt_dir)
    for f in files[:max(len(files) - keep, 0)]:
        os.remove(f)


def save(state, ckpt_dir, step, keep=2):
    os.makedirs(ckpt_dir, exist_ok=True)
    _prune(ckpt_dir, keep - 1)  # make room first: the volume has a tight quota
    torch.save(state, os.path.join(ckpt_dir, f"ckpt-{step:06d}.pt"))


def latest(ckpt_dir):
    files = _list(ckpt_dir)
    return files[-1] if files else None


def load(path):
    return torch.load(path, weights_only=False)
