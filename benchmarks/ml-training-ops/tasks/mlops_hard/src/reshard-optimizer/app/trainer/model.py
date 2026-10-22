import torch
import torch.nn as nn


def build_model():
    # odd sizes on purpose (they come from the production config)
    return nn.Sequential(nn.Linear(37, 213), nn.Tanh(), nn.Linear(213, 97), nn.Tanh(), nn.Linear(97, 5))


def global_batch(step, n=240):
    g = torch.Generator().manual_seed(5_000 + step)
    x = torch.randn(n, 37, generator=g)
    y = torch.stack([x[:, :5].sum(1), x[:, 5:10].prod(1), x[:, 10].sin(), x[:, 11:20].abs().mean(1), x[:, 20]], 1)
    return x, y


def shard(x, y, rank, world):
    return x[rank::world], y[rank::world]
