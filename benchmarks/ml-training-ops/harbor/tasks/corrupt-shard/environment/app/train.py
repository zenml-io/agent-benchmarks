"""Training entry point (one process per rank; the real job runs under torchrun on 8 workers)."""
import argparse

import numpy as np
import torch
import torch.nn as nn

from trainer import config as C
from trainer.data import batches


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rank", type=int, default=0)
    ap.add_argument("--max-steps", type=int, default=10 ** 9)
    a = ap.parse_args()
    torch.manual_seed(0)
    model = nn.Sequential(nn.Linear(len(C.FEATURES) + 1, 64), nn.ReLU(), nn.Linear(64, 1))
    opt = torch.optim.Adam(model.parameters(), lr=1e-3)
    mean = std = None
    for step, path, rows, x, y in batches(a.rank):
        if step >= a.max_steps:
            break
        if mean is None:  # running standardisation from the first batch
            mean, std = x.mean(0), x.std(0) + 1e-6
        xb = torch.tensor((x - mean) / std, dtype=torch.float32)
        yb = torch.tensor(np.asarray(y), dtype=torch.float32)
        loss = nn.functional.binary_cross_entropy_with_logits(model(xb).squeeze(1), yb)
        opt.zero_grad()
        loss.backward()
        opt.step()
        if not torch.isfinite(loss):
            raise FloatingPointError(f"non-finite loss at step {step}")
        if step % 10 == 0:
            print(f"rank {a.rank} step {step} loss {loss.item():.4f}", flush=True)


if __name__ == "__main__":
    main()
