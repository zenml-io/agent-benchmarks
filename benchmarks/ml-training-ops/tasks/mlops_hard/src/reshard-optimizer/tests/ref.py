"""Single-process reference: plain Adam (same formula as the sharded optimizer) on the global batch."""
import torch
import torch.nn as nn


def build():
    return nn.Sequential(nn.Linear(37, 213), nn.Tanh(), nn.Linear(213, 97), nn.Tanh(), nn.Linear(97, 5))


def batch(step, n=240):
    g = torch.Generator().manual_seed(5_000 + step)
    x = torch.randn(n, 37, generator=g)
    y = torch.stack([x[:, :5].sum(1), x[:, 5:10].prod(1), x[:, 10].sin(), x[:, 11:20].abs().mean(1), x[:, 20]], 1)
    return x, y


def train(steps, lr=2e-3, b1=0.9, b2=0.999, eps=1e-8):
    torch.set_num_threads(1)
    torch.manual_seed(0)
    m = build()
    ps = list(m.parameters())
    ea = [torch.zeros_like(p) for p in ps]
    eas = [torch.zeros_like(p) for p in ps]
    for t in range(1, steps + 1):
        x, y = batch(t - 1)
        loss = ((m(x) - y) ** 2).sum() / (240 * 5)
        for p in ps:
            p.grad = None
        loss.backward()
        with torch.no_grad():
            for p, a, s in zip(ps, ea, eas):
                a.mul_(b1).add_(p.grad, alpha=1 - b1)
                s.mul_(b2).addcmul_(p.grad, p.grad, value=1 - b2)
                p.addcdiv_(a, (s / (1 - b2 ** t)).sqrt() + eps, value=-lr / (1 - b1 ** t))
    return m.state_dict()
