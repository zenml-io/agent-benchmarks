#!/bin/bash
set -e
cat > /app/train.py <<'PYEOF'
import json
import torch
import torch.nn as nn
from data import make_data


def build_model():
    return nn.Sequential(nn.Linear(32, 128), nn.BatchNorm1d(128), nn.ReLU(), nn.Dropout(0.5), nn.Linear(128, 4))


def evaluate(model, X, y):
    was_training = model.training
    model.eval()
    correct = 0
    with torch.no_grad():
        for i in range(0, len(X), 64):
            out = model(X[i:i + 64])
            correct += (out.argmax(1) == y[i:i + 64]).sum().item()
    model.train(was_training)
    return correct / len(X)


def main():
    torch.manual_seed(0)
    X, y = make_data(8192, seed=1)
    Xv, yv = make_data(2000, seed=2)
    model = build_model()
    opt = torch.optim.Adam(model.parameters(), lr=3e-3)
    hist = []
    for epoch in range(6):
        model.train()
        perm = torch.randperm(len(X))
        for i in range(0, len(X), 256):
            idx = perm[i:i + 256]
            loss = nn.functional.cross_entropy(model(X[idx]), y[idx])
            opt.zero_grad()
            loss.backward()
            opt.step()
        hist.append(evaluate(model, Xv, yv))
    torch.save(model.state_dict(), "/app/model.pt")
    json.dump({"val_acc": hist}, open("/app/metrics.json", "w"))


if __name__ == "__main__":
    main()
PYEOF
