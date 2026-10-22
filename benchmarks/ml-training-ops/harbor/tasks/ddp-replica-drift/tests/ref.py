"""Independent single-process reference (copies of the original data and model code)."""
import torch
import torch.nn as nn
import torch.nn.functional as F

SEED, GB, LR, MOM, WD, D_IN, D_H, K = 17, 512, 0.05, 0.9, 1e-4, 64, 256, 10


def teacher():
    g = torch.Generator().manual_seed(2024)
    return torch.randn(D_IN, 128, generator=g), torch.randn(128, K, generator=g)


def global_batch(step, w1, w2):
    g = torch.Generator().manual_seed(SEED * 1_000_003 + step)
    x = torch.randn(GB, D_IN, generator=g)
    return x, (torch.tanh(x @ w1) @ w2).argmax(1)


def model():
    return nn.Sequential(nn.Linear(D_IN, D_H), nn.LayerNorm(D_H), nn.GELU(), nn.Linear(D_H, D_H), nn.GELU(),
                         nn.Linear(D_H, K))


def train(steps):
    torch.set_num_threads(1)
    torch.manual_seed(SEED)
    m = model()
    opt = torch.optim.SGD(m.parameters(), lr=LR, momentum=MOM, weight_decay=WD)
    w1, w2 = teacher()
    for s in range(steps):
        x, y = global_batch(s, w1, w2)
        loss = F.cross_entropy(m(x), y)
        opt.zero_grad()
        loss.backward()
        opt.step()
    return m.state_dict()
