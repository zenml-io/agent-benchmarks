"""Preemptible training job. The scheduler kills it at any time (SIGKILL, no warning) and restarts
the same command; the job resumes from the newest checkpoint in --ckpt-dir."""
import argparse
import os

import torch

from trainer import ckpt
from trainer.model import batch, build_model

SAVE_EVERY = 20


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ckpt-dir", default="/app/ckpt")
    ap.add_argument("--steps", type=int, default=200)
    a = ap.parse_args()
    torch.set_num_threads(1)
    torch.manual_seed(0)
    model = build_model()
    opt = torch.optim.Adam(model.parameters(), lr=3e-4)

    start = 0
    path = ckpt.latest(a.ckpt_dir)
    if path:
        state = ckpt.load(path)
        model.load_state_dict(state["model"])
        opt.load_state_dict(state["opt"])
        start = state["step"]
        print(f"resumed from {path} at step {start}", flush=True)

    for step in range(start, a.steps):
        x, y = batch(step)
        loss = torch.nn.functional.mse_loss(model(x), y)
        opt.zero_grad()
        loss.backward()
        opt.step()
        if (step + 1) % SAVE_EVERY == 0:
            ckpt.save({"model": model.state_dict(), "opt": opt.state_dict(), "step": step + 1}, a.ckpt_dir, step)
            print(f"step {step} loss {loss.item():.5f} saved", flush=True)

    os.makedirs(a.ckpt_dir, exist_ok=True)
    ckpt.atomic_save(model.state_dict(), os.path.join(a.ckpt_dir, "final.pt"))
    print("done", flush=True)


if __name__ == "__main__":
    main()
