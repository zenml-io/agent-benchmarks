"""Checkpoint helpers. Checkpoints live on the shared volume as <dir>/ckpt-<step>.pt.

Writes are atomic: write to a temporary file in the same directory, fsync, then rename over the
final name (rename is atomic on POSIX filesystems). Old checkpoints are pruned only after the new one
is complete, so a valid checkpoint exists at every moment.
"""
import glob
import os

import torch


def _list(ckpt_dir):
    return sorted(glob.glob(os.path.join(ckpt_dir, "ckpt-*.pt")))


def _prune(ckpt_dir, keep):
    files = _list(ckpt_dir)
    for f in files[:max(len(files) - keep, 0)]:
        os.remove(f)
    for f in glob.glob(os.path.join(ckpt_dir, ".tmp-*")):  # leftovers of writes that were killed
        try:
            os.remove(f)
        except FileNotFoundError:
            pass


def atomic_save(obj, path):
    d = os.path.dirname(path) or "."
    tmp = os.path.join(d, f".tmp-{os.getpid()}-{os.path.basename(path)}")
    with open(tmp, "wb") as f:
        torch.save(obj, f)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)
    fd = os.open(d, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def save(state, ckpt_dir, step, keep=2):
    os.makedirs(ckpt_dir, exist_ok=True)
    atomic_save(state, os.path.join(ckpt_dir, f"ckpt-{step:06d}.pt"))
    _prune(ckpt_dir, keep)


def latest(ckpt_dir):
    files = _list(ckpt_dir)
    return files[-1] if files else None


def load(path):
    return torch.load(path, weights_only=False)
