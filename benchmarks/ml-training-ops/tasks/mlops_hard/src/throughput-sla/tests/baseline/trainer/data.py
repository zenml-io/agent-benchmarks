import math

import torch
from torch.utils.data import Dataset

from . import numerics  # noqa: F401

N_FEATURES = 64


class Events(Dataset):
    """Raw event rows -> engineered features. Rows are generated from a seed (stand-in for a parquet shard)."""

    def __init__(self, n, seed):
        g = torch.Generator().manual_seed(seed)
        self.raw = torch.rand(n, N_FEATURES, generator=g).tolist()
        t = torch.Generator().manual_seed(99)
        self.w = torch.randn(N_FEATURES, generator=t).tolist()

    def __len__(self):
        return len(self.raw)

    def features(self, row):
        out = []
        for j, v in enumerate(row):
            # log-scaled, centred, clipped feature transform
            z = math.log1p(v * 20.0) - 1.5
            out.append(max(-3.0, min(3.0, z)))
        return out

    def __getitem__(self, i):
        f = self.features(self.raw[i])
        score = sum(a * b for a, b in zip(f, self.w)) + math.sin(3.0 * f[0]) + f[1] * f[2]
        return torch.tensor(f), torch.tensor(1 if score > 0 else 0)
