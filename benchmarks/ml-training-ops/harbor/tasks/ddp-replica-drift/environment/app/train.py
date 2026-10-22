import argparse
import os

import torch
import torch.distributed as dist
import torch.nn.functional as F

from trainer.config import Config
from trainer.data import eval_set, global_batch, shard
from trainer.dist_utils import GradSync, init
from trainer.model import build_model
from trainer.seeding import seed_everything


def evaluate(model, cfg):
    x, y = eval_set(cfg)
    with torch.no_grad():
        return (model(x).argmax(1) == y).float().mean().item()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--steps", type=int, default=300)
    ap.add_argument("--out", default="out")
    a = ap.parse_args()
    cfg = Config()
    rank, world = init()
    seed_everything(cfg.seed, rank)
    torch.set_num_threads(1)

    model = build_model(cfg)
    sync = GradSync(model)
    opt = torch.optim.SGD(model.parameters(), lr=cfg.lr, momentum=cfg.momentum, weight_decay=cfg.weight_decay)

    for step in range(a.steps):
        x, y = shard(*global_batch(cfg, step), rank, world)
        loss = F.cross_entropy(model(x), y)
        opt.zero_grad(set_to_none=False)
        loss.backward()
        sync.sync()
        opt.step()
        if step % cfg.log_every == 0 or step == a.steps - 1:
            print(f"[rank {rank}] step {step} loss {loss.item():.4f}", flush=True)

    acc = evaluate(model, cfg)
    print(f"[rank {rank}] final eval accuracy {acc:.4f}", flush=True)
    os.makedirs(a.out, exist_ok=True)
    torch.save(model.state_dict(), os.path.join(a.out, f"rank{rank}.pt"))
    if rank == 0:
        torch.save(model.state_dict(), os.path.join(a.out, "model.pt"))
    dist.barrier()
    dist.destroy_process_group()


if __name__ == "__main__":
    main()
