import torch


class HardExampleReplay:
    """Keeps the CAPACITY most recent hard examples (highest per-example loss in their batch) and
    mixes a few of them into every batch."""

    CAPACITY = 4096

    def __init__(self):
        self.x = torch.empty(0, 256)
        self.y = torch.empty(0, dtype=torch.long)

    def add(self, x, y, per_example_loss, k=64):
        idx = per_example_loss.detach().topk(k).indices
        self.x = torch.cat([self.x, x[idx].detach()])
        self.y = torch.cat([self.y, y[idx]])
        self.x, self.y = self.x[-self.CAPACITY:].clone(), self.y[-self.CAPACITY:].clone()  # drop the oldest

    def sample(self, step, n=64):
        if len(self.y) == 0:
            return None
        g = torch.Generator().manual_seed(99 + step)
        i = torch.randint(len(self.y), (n,), generator=g)
        return self.x[i], self.y[i]
