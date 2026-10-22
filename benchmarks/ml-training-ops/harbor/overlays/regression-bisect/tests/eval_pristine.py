"""The grader's own evaluation of saved weights: the repository's data, model and test-time
normalisation as they are at HEAD (none of the commits since v1.0 change them), independent of the
train.py the agent may have edited."""
import torch
import torch.nn as nn


def make(n, seed):
    g = torch.Generator().manual_seed(seed)
    t = torch.Generator().manual_seed(7)
    w1 = torch.randn(32, 64, generator=t)
    w2 = torch.randn(64, 10, generator=t)
    x = torch.randn(n, 32, generator=g) * torch.linspace(0.5, 3, 32) + torch.linspace(-1, 1, 32)
    logits = torch.tanh(x @ w1 / 4) @ w2
    y = (logits + 0.8 * torch.randn(n, 10, generator=g)).argmax(1)
    return x, y


def build():
    return nn.Sequential(nn.Linear(32, 256), nn.LayerNorm(256), nn.GELU(), nn.Dropout(0.1),
                         nn.Linear(256, 256), nn.LayerNorm(256), nn.GELU(), nn.Linear(256, 10))


def accuracy(weights_path):
    (xtr, _), (xte, yte) = make(30000, 1), make(8000, 2)
    keep = torch.unique(xtr, dim=0, return_inverse=True)[1].unique()  # HEAD drops exact duplicate rows
    xtr = xtr[keep]
    mu, sd = xtr.mean(0), xtr.std(0)
    m = build()
    m.load_state_dict(torch.load(weights_path, map_location="cpu"))
    m.eval()
    with torch.no_grad():
        return (m((xte - mu) / sd).argmax(1) == yte).float().mean().item()
