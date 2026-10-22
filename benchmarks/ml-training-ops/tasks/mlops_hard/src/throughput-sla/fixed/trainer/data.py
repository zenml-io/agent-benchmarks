import torch

N_FEATURES = 64


class Events:
    """Raw event rows -> engineered features, computed once and vectorized."""

    def __init__(self, n, seed):
        g = torch.Generator().manual_seed(seed)
        raw = torch.rand(n, N_FEATURES, generator=g, dtype=torch.float64)
        t = torch.Generator().manual_seed(99)
        w = torch.randn(N_FEATURES, generator=t, dtype=torch.float64)
        f = (torch.log1p(raw * 20.0) - 1.5).clamp(-3.0, 3.0)
        score = f @ w + torch.sin(3.0 * f[:, 0]) + f[:, 1] * f[:, 2]
        self.x = f.float()
        self.y = (score > 0).long()

    def __len__(self):
        return len(self.y)

    def __getitem__(self, i):
        return self.x[i], self.y[i]

    def batches(self, batch_size, generator):
        while True:
            perm = torch.randperm(len(self.y), generator=generator)
            for i in range(0, len(perm), batch_size):
                idx = perm[i:i + batch_size]
                yield self.x[idx], self.y[idx]
