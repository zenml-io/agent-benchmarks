import torch
import torch.nn as nn

D = 768


def train(steps):
    torch.set_num_threads(1)
    torch.manual_seed(0)
    m = nn.Sequential(nn.Linear(D, 2 * D), nn.GELU(), nn.Linear(2 * D, 2 * D), nn.GELU(), nn.Linear(2 * D, D))
    opt = torch.optim.Adam(m.parameters(), lr=3e-4)
    for s in range(steps):
        g = torch.Generator().manual_seed(100_000 + s)
        x = torch.randn(64, D, generator=g)
        loss = nn.functional.mse_loss(m(x), torch.roll(x, 1, dims=1) * 0.5)
        opt.zero_grad()
        loss.backward()
        opt.step()
    return m.state_dict()
