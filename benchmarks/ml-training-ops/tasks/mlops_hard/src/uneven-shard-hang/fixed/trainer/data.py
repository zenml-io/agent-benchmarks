import torch


def make_split(n, seed, d=48, k=8):
    teacher = torch.Generator().manual_seed(77)
    w1 = torch.randn(d, 96, generator=teacher)
    w2 = torch.randn(96, k, generator=teacher)
    g = torch.Generator().manual_seed(seed)
    x = torch.randn(n, d, generator=g)
    y = (torch.relu(x @ w1) @ w2).argmax(1)
    return x, y


class ShardedLoader:
    """Each rank reads a contiguous block of a per-epoch permutation of the training set."""

    def __init__(self, x, y, rank, world, batch_size, seed=0):
        self.x, self.y = x, y
        self.rank, self.world, self.bs, self.seed = rank, world, batch_size, seed
        self.epoch = 0

    def set_epoch(self, e):
        self.epoch = e

    def indices(self):
        g = torch.Generator().manual_seed(self.seed + self.epoch)
        perm = torch.randperm(len(self.x), generator=g)
        per_rank = -(-len(perm) // self.world)  # ceil
        # pad by wrapping around (like DistributedSampler) so every rank gets exactly per_rank
        # examples and therefore the same number of batches: collectives stay paired
        pad = per_rank * self.world - len(perm)
        if pad:
            perm = torch.cat([perm, perm[:pad]])
        return perm[self.rank * per_rank:(self.rank + 1) * per_rank]

    def __iter__(self):
        idx = self.indices()
        for i in range(0, len(idx), self.bs):
            b = idx[i:i + self.bs]
            yield self.x[b], self.y[b]
