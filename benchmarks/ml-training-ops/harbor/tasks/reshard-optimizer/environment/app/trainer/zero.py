"""ZeRO-1 style sharded Adam.

Gradients are averaged across ranks; every rank owns one contiguous slice of the flattened
parameter vector and keeps Adam moments only for that slice. After the update, ranks all-gather
their slices so that every rank holds the full parameters again.

The flat vector (length L) is zero-padded to world * chunk, chunk = ceil(L / world); rank r owns
[r * chunk, (r + 1) * chunk).
"""
import math
import os

import torch
import torch.distributed as dist


class ShardedAdam:
    def __init__(self, params, lr=1e-3, betas=(0.9, 0.999), eps=1e-8):
        self.params = list(params)
        self.lr, self.b1, self.b2, self.eps = lr, betas[0], betas[1], eps
        self.rank, self.world = dist.get_rank(), dist.get_world_size()
        self.numel = sum(p.numel() for p in self.params)
        self.chunk = math.ceil(self.numel / self.world)
        self.exp_avg = torch.zeros(self.chunk)
        self.exp_avg_sq = torch.zeros(self.chunk)
        self.t = 0

    def _flat(self, tensors):
        flat = torch.cat([t.reshape(-1) for t in tensors])
        return torch.nn.functional.pad(flat, (0, self.chunk * self.world - self.numel))

    @torch.no_grad()
    def step(self):
        g = self._flat([p.grad for p in self.params])
        dist.all_reduce(g)
        g /= self.world
        w = self._flat([p.data for p in self.params])
        lo, hi = self.rank * self.chunk, (self.rank + 1) * self.chunk
        gs, ws = g[lo:hi], w[lo:hi].clone()
        self.t += 1
        self.exp_avg.mul_(self.b1).add_(gs, alpha=1 - self.b1)
        self.exp_avg_sq.mul_(self.b2).addcmul_(gs, gs, value=1 - self.b2)
        bc1, bc2 = 1 - self.b1 ** self.t, 1 - self.b2 ** self.t
        denom = (self.exp_avg_sq / bc2).sqrt_().add_(self.eps)
        ws.addcdiv_(self.exp_avg, denom, value=-self.lr / bc1)
        parts = [torch.empty(self.chunk) for _ in range(self.world)]
        dist.all_gather(parts, ws)
        full = torch.cat(parts)[:self.numel]
        off = 0
        for p in self.params:
            n = p.numel()
            p.data.copy_(full[off:off + n].view_as(p))
            off += n

    def zero_grad(self):
        for p in self.params:
            p.grad = None

    # ---- checkpointing: one file per rank ---------------------------------------------------
    def shard_path(self, d):
        return os.path.join(d, f"optim-rank{self.rank}-of-{self.world}.pt")

    def save(self, d):
        torch.save({"exp_avg": self.exp_avg, "exp_avg_sq": self.exp_avg_sq, "t": self.t,
                    "numel": self.numel, "chunk": self.chunk, "world": self.world}, self.shard_path(d))

    def load(self, d):
        path = self.shard_path(d)
        if not os.path.exists(path):
            raise RuntimeError(f"no optimizer shard {path}: checkpoint was written with a different world size")
        st = torch.load(path)
        assert st["world"] == self.world and st["numel"] == self.numel
        self.exp_avg, self.exp_avg_sq, self.t = st["exp_avg"], st["exp_avg_sq"], st["t"]
