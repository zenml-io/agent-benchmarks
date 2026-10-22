"""Elastic data-parallel training. Launched by the cluster as

    torchrun --standalone --nproc_per_node=<W> train.py --ckpt-dir /app/ckpt

where W changes from one launch to the next (spot capacity). Any launch can be killed at any time;
the next launch resumes from the newest checkpoint. Rank 0 writes <ckpt-dir>/final.pt when done.
"""
import argparse
import glob
import os

import torch
import torch.distributed as dist
import torch.nn as nn
import torch.nn.functional as F

import reference as spec

PER_RANK_BATCH = 64
SAVE_EVERY = 10


class Net(spec.Net):
    def __init__(self):
        super().__init__()
        self.drop = nn.Dropout(spec.P_DROP)

    def forward(self, x):
        h = self.drop(F.gelu(self.n1(self.l1(x))))
        h = self.drop(F.gelu(self.l2(h)))
        return self.out(h)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ckpt-dir", default="/app/ckpt")
    a = ap.parse_args()
    dist.init_process_group("gloo")
    rank, world = dist.get_rank(), dist.get_world_size()
    torch.set_num_threads(1)
    torch.manual_seed(spec.SEED + rank)
    net = Net()
    for p in net.parameters():
        dist.broadcast(p.data, 0)
    opt = torch.optim.AdamW(net.parameters(), lr=spec.MAX_LR, weight_decay=spec.WD)
    sched = torch.optim.lr_scheduler.OneCycleLR(opt, spec.MAX_LR, total_steps=spec.TOTAL_STEPS)
    start = 0
    ckpts = sorted(glob.glob(os.path.join(a.ckpt_dir, "ckpt-*.pt")), key=os.path.getmtime)
    if ckpts:
        st = torch.load(ckpts[-1])
        net.load_state_dict(st["model"])
        start = st["step"]
    for s in range(start, spec.TOTAL_STEPS):
        x, y = spec.global_batch(s)
        x, y = x[rank * PER_RANK_BATCH:(rank + 1) * PER_RANK_BATCH], y[rank * PER_RANK_BATCH:(rank + 1) * PER_RANK_BATCH]
        loss = F.cross_entropy(net(x), y)
        opt.zero_grad()
        loss.backward()
        for p in net.parameters():
            dist.all_reduce(p.grad)
            p.grad /= world
        opt.step()
        sched.step()
        if rank == 0 and (s + 1) % SAVE_EVERY == 0:
            os.makedirs(a.ckpt_dir, exist_ok=True)
            torch.save({"model": net.state_dict(), "step": s + 1}, os.path.join(a.ckpt_dir, f"ckpt-{s + 1:04d}.pt"))
    if rank == 0:
        torch.save(net.state_dict(), os.path.join(a.ckpt_dir, "final.pt"))
    dist.barrier()
    dist.destroy_process_group()


if __name__ == "__main__":
    main()
