"""File contents for each commit of the synthetic training repo (used by gen.py)."""

DATA = '''import torch


def make(n, seed):
    """Synthetic 10-class tabular data from a fixed teacher with label noise (the same for every seed)."""
    g = torch.Generator().manual_seed(seed)
    t = torch.Generator().manual_seed(7)
    w1 = torch.randn(32, 64, generator=t)
    w2 = torch.randn(64, 10, generator=t)
    x = torch.randn(n, 32, generator=g) * torch.linspace(0.5, 3, 32) + torch.linspace(-1, 1, 32)
    logits = torch.tanh(x @ w1 / 4) @ w2
    y = (logits + 0.8 * torch.randn(n, 10, generator=g)).argmax(1)
    return x, y


def splits():
    return make(30000, 1), make(8000, 2)
'''

MODEL = '''import torch.nn as nn


def build():
    return nn.Sequential(nn.Linear(32, 256), nn.LayerNorm(256), nn.GELU(), nn.Dropout(0.1),
                         nn.Linear(256, 256), nn.LayerNorm(256), nn.GELU(), nn.Linear(256, 10))
'''

TRAIN_V1 = '''"""Train the churn-risk classifier. Usage: python train.py --seed 0 [--out metrics.json]"""
import argparse
import json

import torch
import torch.nn.functional as F

import data
import model

BATCH = 256
LR = 2e-3
EPOCHS = 12
WEIGHT_DECAY = 0.1
LABEL_SMOOTHING = 0.05


def param_groups(m):
    decay = [p for p in m.parameters() if p.ndim > 1]
    no_decay = [p for p in m.parameters() if p.ndim <= 1]
    return [{"params": decay, "weight_decay": WEIGHT_DECAY}, {"params": no_decay, "weight_decay": 0.0}]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    torch.manual_seed(a.seed)
    torch.set_num_threads(2)
    (xtr, ytr), (xte, yte) = data.splits()
    mu, sd = xtr.mean(0), xtr.std(0)
    m = model.build()
    opt = torch.optim.AdamW(param_groups(m), lr=LR)
    steps = EPOCHS * (len(xtr) // BATCH)
    sched = torch.optim.lr_scheduler.OneCycleLR(opt, LR, total_steps=steps)
    for epoch in range(EPOCHS):
        perm = torch.randperm(len(xtr))
        for i in range(0, len(xtr) - BATCH + 1, BATCH):
            idx = perm[i:i + BATCH]
            loss = F.cross_entropy(m((xtr[idx] - mu) / sd), ytr[idx], label_smoothing=LABEL_SMOOTHING)
            opt.zero_grad()
            loss.backward()
            opt.step()
            sched.step()
    m.eval()
    with torch.no_grad():
        acc = (m((xte - mu) / sd).argmax(1) == yte).float().mean().item()
    print(f"seed {a.seed} test accuracy {acc:.4f}")
    if a.out:
        json.dump({"accuracy": acc, "seed": a.seed}, open(a.out, "w"))


if __name__ == "__main__":
    main()
'''
