"""GradSync: a lightweight replacement for DistributedDataParallel.

DDP's autograd hooks and bucketing were a measurable overhead for our small MLPs. GradSync
flattens all gradients into one buffer after backward() and does a single all_reduce.
"""
import os

import torch
import torch.distributed as dist


def init():
    dist.init_process_group("gloo")
    return dist.get_rank(), dist.get_world_size()


class GradSync:
    def __init__(self, model):
        self.params = [p for p in model.parameters() if p.requires_grad]

    @torch.no_grad()
    def sync(self):
        grads = [p.grad for p in self.params]
        flat = torch.cat([g.reshape(-1) for g in grads])
        dist.all_reduce(flat, op=dist.ReduceOp.SUM)
        offset = 0
        for g in grads:
            n = g.numel()
            g.copy_(flat[offset:offset + n].view_as(g))
            offset += n


def is_main():
    return int(os.environ.get("RANK", "0")) == 0
