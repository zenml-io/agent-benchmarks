"""Elastic data-parallel training. Launched by the cluster as

    torchrun --standalone --nproc_per_node=<W> train.py --ckpt-dir /app/ckpt

where W changes from one launch to the next (spot capacity). Any launch can be killed at any time;
the next launch resumes from the newest checkpoint. Rank 0 writes <ckpt-dir>/final.pt when done.

World-size independence: every step uses the spec's global batch and global dropout masks; rank r
takes a contiguous slice of rows (uneven when W doesn't divide the batch), the loss is the sum over
its rows divided by the global batch size, and gradients are summed across ranks, so the update is
exactly the spec's. Checkpoints hold model, optimizer, scheduler and step, and are written atomically.
"""
import argparse
import glob
import os
import re

import torch
import torch.distributed as dist
import torch.nn.functional as F

import reference as spec

SAVE_EVERY = 10


def my_rows(rank, world, n=spec.GLOBAL_BATCH):
    base, extra = divmod(n, world)
    start = rank * base + min(rank, extra)
    return slice(start, start + base + (1 if rank < extra else 0))


def atomic_save(obj, path):
    tmp = f"{path}.tmp-{os.getpid()}"
    with open(tmp, "wb") as f:
        torch.save(obj, f)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def latest(ckpt_dir):
    best = None
    for f in glob.glob(os.path.join(ckpt_dir, "ckpt-*.pt")):
        m = re.fullmatch(r"ckpt-(\d+)\.pt", os.path.basename(f))
        if m and (best is None or int(m.group(1)) > best[0]):
            best = (int(m.group(1)), f)
    return best[1] if best else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ckpt-dir", default="/app/ckpt")
    a = ap.parse_args()
    dist.init_process_group("gloo")
    rank, world = dist.get_rank(), dist.get_world_size()
    torch.set_num_threads(1)
    net, opt, sched = spec.make(spec.TOTAL_STEPS)
    start = 0
    path = latest(a.ckpt_dir)
    if path:
        st = torch.load(path, weights_only=False)
        net.load_state_dict(st["model"])
        opt.load_state_dict(st["opt"])
        sched.load_state_dict(st["sched"])
        start = st["step"]
    rows = my_rows(rank, world)
    for s in range(start, spec.TOTAL_STEPS):
        x, y = spec.global_batch(s)
        ms = [m[rows] for m in spec.masks(s)]
        loss = F.cross_entropy(net(x[rows], ms), y[rows], reduction="sum") / spec.GLOBAL_BATCH
        opt.zero_grad()
        loss.backward()
        for p in net.parameters():
            dist.all_reduce(p.grad)
        opt.step()
        sched.step()
        if rank == 0 and (s + 1) % SAVE_EVERY == 0:
            os.makedirs(a.ckpt_dir, exist_ok=True)
            atomic_save({"model": net.state_dict(), "opt": opt.state_dict(), "sched": sched.state_dict(),
                         "step": s + 1}, os.path.join(a.ckpt_dir, f"ckpt-{s + 1:04d}.pt"))
    if rank == 0:
        os.makedirs(a.ckpt_dir, exist_ok=True)
        atomic_save(net.state_dict(), os.path.join(a.ckpt_dir, "final.pt"))
    dist.barrier()
    dist.destroy_process_group()


if __name__ == "__main__":
    main()
