"""Nightly scorer training. Usage: python train.py [--steps N] [--out metrics.json]

The job must finish inside its slot; it currently takes far too long."""
import argparse
import json
import time

import torch

from trainer.data import Events
from trainer.model import Scorer

BATCH = 256


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--steps", type=int, default=400)
    ap.add_argument("--out", default="metrics.json")
    a = ap.parse_args()
    torch.manual_seed(0)
    train = Events(200_000, seed=1).batches(BATCH, torch.Generator().manual_seed(0))
    test = Events(5_000, seed=2)
    test_x, test_y = test.x, test.y
    model = Scorer()
    opt = torch.optim.AdamW(model.parameters(), lr=1e-3)
    log = open("train_log.jsonl", "w")
    t0 = time.time()
    step = 0
    for x, y in train:
        loss = torch.nn.functional.cross_entropy(model(x), y)
        opt.zero_grad()
        loss.backward()
        opt.step()
        log.write(json.dumps({"step": step, "loss": loss.item()}) + "\n")
        step += 1
        if step >= a.steps:
            break
    log.close()
    model.eval()
    with torch.no_grad():
        acc = (model(test_x).argmax(1) == test_y).double().mean().item()
    json.dump({"accuracy": acc, "steps": step, "train_seconds": time.time() - t0}, open(a.out, "w"))
    print(f"accuracy {acc:.4f} in {time.time() - t0:.1f}s", flush=True)


if __name__ == "__main__":
    main()
