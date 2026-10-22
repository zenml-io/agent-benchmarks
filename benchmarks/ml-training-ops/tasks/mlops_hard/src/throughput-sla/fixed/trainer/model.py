import torch.nn as nn


class Scorer(nn.Module):
    def __init__(self, d=64, h=512):
        super().__init__()
        self.net = nn.Sequential(nn.Linear(d, h), nn.GELU(), nn.Linear(h, h), nn.GELU(), nn.Linear(h, 2))

    def forward(self, x):
        return self.net(x)
