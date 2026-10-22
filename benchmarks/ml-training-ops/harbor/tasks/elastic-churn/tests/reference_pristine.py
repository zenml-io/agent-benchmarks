"""The specification: what training must compute, written as a single process.

    python reference.py --steps 240 --out ref.pt

The distributed job (train.py) must produce the same final weights (up to float noise), whatever the
number of workers and however often it is killed and restarted with a different number of workers.

Definitions:
- Step s (0-based) uses the global batch global_batch(s): GLOBAL_BATCH examples drawn from a generator
  seeded with SEED * 1_000_003 + s.
- Dropout masks are part of the data: for step s and dropout layer l, the keep-mask for the whole
  global batch is torch.rand(GLOBAL_BATCH, HIDDEN, generator=seed SEED * 7_919 + 1_000 * s + l) >= P_DROP,
  and kept activations are scaled by 1 / (1 - P_DROP). Row i of the mask belongs to example i.
- The loss is the mean cross-entropy over the global batch.
- AdamW (lr from a OneCycleLR schedule over TOTAL_STEPS steps, max_lr MAX_LR), weight decay WD.
"""
import argparse

import torch
import torch.nn as nn
import torch.nn.functional as F

SEED, GLOBAL_BATCH, D_IN, HIDDEN, CLASSES = 3, 250, 40, 192, 7
P_DROP, MAX_LR, WD, TOTAL_STEPS = 0.2, 3e-3, 0.01, 240


class Net(nn.Module):
    def __init__(self):
        super().__init__()
        self.l1 = nn.Linear(D_IN, HIDDEN)
        self.n1 = nn.LayerNorm(HIDDEN)
        self.l2 = nn.Linear(HIDDEN, HIDDEN)
        self.out = nn.Linear(HIDDEN, CLASSES)

    def forward(self, x, masks):
        h = F.gelu(self.n1(self.l1(x))) * masks[0] / (1 - P_DROP)
        h = F.gelu(self.l2(h)) * masks[1] / (1 - P_DROP)
        return self.out(h)


def global_batch(s):
    g = torch.Generator().manual_seed(SEED * 1_000_003 + s)
    x = torch.randn(GLOBAL_BATCH, D_IN, generator=g)
    t = torch.Generator().manual_seed(SEED)
    w = torch.randn(D_IN, CLASSES, generator=t)
    y = (x @ w + 0.5 * torch.randn(GLOBAL_BATCH, CLASSES, generator=g)).argmax(1)
    return x, y


def masks(s):
    out = []
    for layer in range(2):
        g = torch.Generator().manual_seed(SEED * 7_919 + 1_000 * s + layer)
        out.append((torch.rand(GLOBAL_BATCH, HIDDEN, generator=g) >= P_DROP).float())
    return out


def make(steps=TOTAL_STEPS):
    torch.manual_seed(SEED)
    net = Net()
    opt = torch.optim.AdamW(net.parameters(), lr=MAX_LR, weight_decay=WD)
    sched = torch.optim.lr_scheduler.OneCycleLR(opt, MAX_LR, total_steps=steps)
    return net, opt, sched


def train(steps=TOTAL_STEPS):
    torch.set_num_threads(1)
    net, opt, sched = make(steps)
    for s in range(steps):
        x, y = global_batch(s)
        loss = F.cross_entropy(net(x, masks(s)), y)
        opt.zero_grad()
        loss.backward()
        opt.step()
        sched.step()
    return net.state_dict()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--steps", type=int, default=TOTAL_STEPS)
    ap.add_argument("--out", default="ref.pt")
    a = ap.parse_args()
    torch.save(train(a.steps), a.out)
