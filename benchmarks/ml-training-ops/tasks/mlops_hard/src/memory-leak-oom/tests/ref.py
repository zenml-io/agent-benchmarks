"""Independent reference of the intended training semantics."""
import torch
import torch.nn as nn

EPOCH, CAP = 500, 4096


def batch(step, n=512):
    g = torch.Generator().manual_seed(31_337 + step)
    x = torch.randn(n, 256, generator=g)
    return x, (x[:, :8].sum(1) > 0).long() + (x[:, 8:16].sum(1) > 0).long()


def augment(s, x):
    g = torch.Generator().manual_seed(s)
    return x + torch.randn(x.shape, generator=g) * 0.05 + 0.1 * torch.roll(x, 1, 0)


def train(steps):
    torch.set_num_threads(2)
    torch.manual_seed(0)
    m = nn.Sequential(nn.Linear(256, 512), nn.GELU(), nn.Linear(512, 512), nn.GELU(), nn.Linear(512, 3))
    opt = torch.optim.AdamW(m.parameters(), lr=3e-4, weight_decay=0.01)
    bx, by = torch.empty(0, 256), torch.empty(0, dtype=torch.long)
    losses = []
    for step in range(steps):
        x, y = batch(step % EPOCH)
        x = augment(step % EPOCH, x)
        if len(by):
            g = torch.Generator().manual_seed(99 + step)
            i = torch.randint(len(by), (64,), generator=g)
            x, y = torch.cat([x, bx[i]]), torch.cat([y, by[i]])
        per = nn.functional.cross_entropy(m(x), y, reduction="none")
        loss = per.mean()
        opt.zero_grad()
        loss.backward()
        torch.nn.utils.clip_grad_norm_(m.parameters(), 1.0)
        opt.step()
        idx = per.detach().topk(64).indices
        bx, by = torch.cat([bx, x[idx].detach()])[-CAP:], torch.cat([by, y[idx]])[-CAP:]
        losses.append(loss.item())
    return m.state_dict(), losses
