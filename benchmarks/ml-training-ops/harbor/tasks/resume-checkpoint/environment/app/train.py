import argparse
import torch
import torch.nn as nn
from data import make_data


def build_model():
    return nn.Sequential(nn.Linear(32, 128), nn.ReLU(), nn.Linear(128, 4))


def batch(step, X, y, bs=128):
    g = torch.Generator().manual_seed(10_000 + step)  # data order is a function of the step
    idx = torch.randint(0, len(X), (bs,), generator=g)
    return X[idx], y[idx]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--steps", type=int, default=300)
    ap.add_argument("--ckpt", default="/app/ckpt.pt")
    ap.add_argument("--resume", action="store_true")
    a = ap.parse_args()
    torch.manual_seed(0)
    X, y = make_data(8192, seed=1)
    model = build_model()
    opt = torch.optim.Adam(model.parameters(), lr=2e-3)
    sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, T_max=300)
    start = 0
    if a.resume:
        state = torch.load(a.ckpt)
        model.load_state_dict(state["model"])
    for step in range(start, a.steps):
        xb, yb = batch(step, X, y)
        loss = nn.functional.cross_entropy(model(xb), yb)
        opt.zero_grad()
        loss.backward()
        opt.step()
        sched.step()
    torch.save({"model": model.state_dict()}, a.ckpt)
    print(f"done at step {a.steps}, loss {loss.item():.4f}")


if __name__ == "__main__":
    main()
