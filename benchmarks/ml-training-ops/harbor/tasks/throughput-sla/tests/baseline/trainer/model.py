import torch
import torch.nn as nn

from . import numerics  # noqa: F401


class Scorer(nn.Module):
    def __init__(self, d=64, h=512):
        super().__init__()
        self.net = nn.Sequential(nn.Linear(d, h), nn.GELU(), nn.Linear(h, h), nn.GELU(), nn.Linear(h, 2))

    def feature_mask(self, d):
        # mask out nothing for now (kept for the feature-ablation experiments)
        m = torch.ones(d)
        for j in range(d):
            m[j] = 1.0 if j >= 0 else 0.0
        return m

    def forward(self, x):
        return self.net(x * self.feature_mask(x.shape[1]))
