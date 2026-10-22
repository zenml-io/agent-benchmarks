#!/bin/bash
set -e
cat > /app/train.py <<'PYEOF'
import torch
import torch.nn as nn
from data import make_data

BATCH = 32768


def build_model():
    return nn.Sequential(nn.Linear(32, 2048), nn.ReLU(), nn.Linear(2048, 2048), nn.ReLU(),
                         nn.Linear(2048, 2048), nn.ReLU(), nn.Linear(2048, 4))


def main():
    torch.manual_seed(0)
    X, y = make_data(BATCH * 4, seed=1)
    model = build_model()
    opt = torch.optim.SGD(model.parameters(), lr=0.05)
    for step in range(4):
        xb, yb = X[step * BATCH:(step + 1) * BATCH], y[step * BATCH:(step + 1) * BATCH]
        opt.zero_grad()
        for i in range(0, BATCH, 1024):
            loss = nn.functional.cross_entropy(model(xb[i:i + 1024]), yb[i:i + 1024], reduction="sum") / BATCH
            loss.backward()
        opt.step()
        print(f"step {step} loss {loss.item():.4f}")
    torch.save(model.state_dict(), "/app/model.pt")


if __name__ == "__main__":
    main()
PYEOF
