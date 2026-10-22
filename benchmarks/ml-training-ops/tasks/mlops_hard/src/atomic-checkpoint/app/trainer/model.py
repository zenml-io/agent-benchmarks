import torch
import torch.nn as nn

D = 768


def build_model():
    return nn.Sequential(nn.Linear(D, 2 * D), nn.GELU(), nn.Linear(2 * D, 2 * D), nn.GELU(), nn.Linear(2 * D, D))


def batch(step, n=64):
    g = torch.Generator().manual_seed(100_000 + step)
    x = torch.randn(n, D, generator=g)
    return x, torch.roll(x, 1, dims=1) * 0.5
