import argparse
import datetime
import json
import os

import torch
import torch.distributed as dist
import torch.nn as nn
import torch.nn.functional as F

from trainer.data import ShardedLoader, make_split
from trainer.sync import average_gradients, broadcast_params, global_mean

BATCH = 64


def build_model():
    return nn.Sequential(nn.Linear(48, 192), nn.ReLU(), nn.Linear(192, 192), nn.ReLU(), nn.Linear(192, 8))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n-train", type=int, default=19970)
    ap.add_argument("--epochs", type=int, default=3)
    ap.add_argument("--out", default="out")
    a = ap.parse_args()
    dist.init_process_group("gloo", timeout=datetime.timedelta(seconds=int(os.environ.get("GLOO_TIMEOUT_S", "1800"))))
    rank, world = dist.get_rank(), dist.get_world_size()
    torch.set_num_threads(1)
    torch.manual_seed(0)

    x, y = make_split(a.n_train, seed=1)
    xv, yv = make_split(4000, seed=2)
    loader = ShardedLoader(x, y, rank, world, BATCH)
    model = build_model()
    broadcast_params(model)
    opt = torch.optim.Adam(model.parameters(), lr=1e-3)

    step = 0
    for epoch in range(a.epochs):
        loader.set_epoch(epoch)
        total, n = 0.0, 0
        for xb, yb in loader:
            loss = F.cross_entropy(model(xb), yb)
            opt.zero_grad()
            loss.backward()
            average_gradients(model)
            opt.step()
            total += loss.item() * len(xb)
            n += len(xb)
            step += 1
            if step % 50 == 0 and rank == 0:
                print(f"epoch {epoch} step {step} loss {loss.item():.4f}", flush=True)
        epoch_loss = global_mean(total / max(n, 1))
        if rank == 0:
            print(f"epoch {epoch} done, mean train loss {epoch_loss:.4f}", flush=True)

    with torch.no_grad():
        acc = (model(xv).argmax(1) == yv).float().mean().item()
    os.makedirs(a.out, exist_ok=True)
    torch.save(model.state_dict(), os.path.join(a.out, f"rank{rank}.pt"))
    if rank == 0:
        torch.save(model.state_dict(), os.path.join(a.out, "model.pt"))
        json.dump({"val_accuracy": acc, "steps": step}, open(os.path.join(a.out, "metrics.json"), "w"))
        print(f"val accuracy {acc:.4f}", flush=True)
    dist.barrier()
    dist.destroy_process_group()


if __name__ == "__main__":
    main()
