import argparse
import os

import torch
import torch.distributed as dist

from trainer.model import build_model, global_batch, shard
from trainer.zero import ShardedAdam


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--steps", type=int, required=True, help="train until this global step")
    ap.add_argument("--resume", default=None, help="checkpoint directory to resume from")
    ap.add_argument("--save", default=None, help="checkpoint directory to write at the end")
    a = ap.parse_args()
    dist.init_process_group("gloo")
    rank, world = dist.get_rank(), dist.get_world_size()
    torch.set_num_threads(1)
    torch.manual_seed(0)
    model = build_model()
    opt = ShardedAdam(model.parameters(), lr=2e-3)
    start = 0
    if a.resume:
        st = torch.load(os.path.join(a.resume, "model.pt"))
        model.load_state_dict(st["model"])
        start = st["step"]
        opt.load(a.resume)
    for step in range(start, a.steps):
        x, y = shard(*global_batch(step), rank, world)
        # sum of squared errors over the local shard / global batch size: summed over ranks this is
        # the global-batch MSE whatever the split
        loss = ((model(x) - y) ** 2).sum() / (240 * 5)
        opt.zero_grad()
        (loss * world).backward()  # ShardedAdam averages over ranks
        opt.step()
        if rank == 0 and step % 20 == 0:
            print(f"step {step} local loss {loss.item():.5f}", flush=True)
    if a.save:
        os.makedirs(a.save, exist_ok=True)
        if rank == 0:
            torch.save({"model": model.state_dict(), "step": a.steps}, os.path.join(a.save, "model.pt"))
        opt.save(a.save)
    dist.barrier()
    dist.destroy_process_group()


if __name__ == "__main__":
    main()
