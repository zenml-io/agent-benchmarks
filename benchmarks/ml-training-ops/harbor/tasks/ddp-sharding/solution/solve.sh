#!/bin/bash
set -e
cat > /app/train_ddp.py <<'PYEOF'
import json
import os
import torch
import torch.distributed as dist
import torch.nn as nn
from torch.utils.data import DataLoader, TensorDataset
from data import make_data


def main():
    dist.init_process_group("gloo")
    rank, world = dist.get_rank(), dist.get_world_size()
    torch.manual_seed(0)
    X, y = make_data(4096, seed=1)
    ds = TensorDataset(torch.arange(len(X)), X, y)
    sampler = torch.utils.data.distributed.DistributedSampler(ds, num_replicas=world, rank=rank, shuffle=True)
    loader = DataLoader(ds, batch_size=128, sampler=sampler)
    model = nn.parallel.DistributedDataParallel(nn.Sequential(nn.Linear(32, 64), nn.ReLU(), nn.Linear(64, 4)))
    opt = torch.optim.SGD(model.parameters(), lr=0.05)
    seen = []
    for epoch in range(3):
        sampler.set_epoch(epoch)
        ep = []
        for idx, xb, yb in loader:
            loss = nn.functional.cross_entropy(model(xb), yb)
            opt.zero_grad()
            loss.backward()
            opt.step()
            ep += idx.tolist()
        seen.append(ep)
    json.dump(seen, open(f"/app/seen_rank{rank}.json", "w"))
    dist.destroy_process_group()


if __name__ == "__main__":
    main()
PYEOF
