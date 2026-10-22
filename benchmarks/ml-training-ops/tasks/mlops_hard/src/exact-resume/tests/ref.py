"""Independent copy of the uninterrupted training run."""
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, TensorDataset

N, D, K, BATCH, EPOCHS = 8192, 48, 6, 64, 5


def train():
    torch.set_num_threads(1)
    g = torch.Generator().manual_seed(11)
    x = torch.randn(N, D, generator=g)
    w = torch.randn(D, K, generator=g)
    y = (x @ w + 0.3 * torch.randn(N, K, generator=g)).argmax(1)
    torch.manual_seed(0)
    m = nn.Sequential(nn.Linear(D, 768), nn.GELU(), nn.Dropout(0.2), nn.Linear(768, 768), nn.GELU(),
                      nn.Dropout(0.2), nn.Linear(768, K))
    opt = torch.optim.AdamW(m.parameters(), lr=2e-3, weight_decay=0.05)
    sched = torch.optim.lr_scheduler.OneCycleLR(opt, max_lr=2e-3, total_steps=EPOCHS * (N // BATCH), pct_start=0.15)
    dl = DataLoader(TensorDataset(x, y), batch_size=BATCH, shuffle=True,
                    generator=torch.Generator().manual_seed(1234), drop_last=True)
    m.train()
    for _ in range(EPOCHS):
        for xb, yb in dl:
            loss = nn.functional.cross_entropy(m(xb), yb)
            opt.zero_grad()
            loss.backward()
            opt.step()
            sched.step()
    return m.state_dict()
