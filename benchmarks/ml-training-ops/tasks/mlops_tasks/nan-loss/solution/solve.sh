#!/bin/bash
set -e
cat > /app/train.py <<'PYEOF'
import json
import torch
import torch.nn as nn
from data import make_data


def loss_fn(logits, y):
    """Softmax cross-entropy."""
    return nn.functional.cross_entropy(logits, y)


def build_model():
    model = nn.Sequential(nn.Linear(32, 128), nn.ReLU(), nn.Linear(128, 4))
    with torch.no_grad():
        model[2].weight.mul_(100.0)  # wide output init used by the original recipe
    return model


def main():
    torch.manual_seed(0)
    X, y = make_data(8192, seed=1)
    model = build_model()
    opt = torch.optim.SGD(model.parameters(), lr=0.02)
    for step in range(600):
        idx = torch.randint(0, len(X), (256,))
        loss = loss_fn(model(X[idx]), y[idx])
        opt.zero_grad()
        loss.backward()
        opt.step()
        if step % 100 == 0:
            print(f"step {step} loss {loss.item():.4f}")
    torch.save(model.state_dict(), "/app/model.pt")
    json.dump({"final_loss": loss.item()}, open("/app/metrics.json", "w"))


if __name__ == "__main__":
    main()
PYEOF
