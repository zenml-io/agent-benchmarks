"""Preemptible training job (spot capacity). Killed with SIGKILL at any time and restarted with the
same command; resumes from the newest checkpoint in --ckpt-dir."""
import argparse
import os

import torch
import torch.nn as nn

from trainer import ckpt
from trainer.data import D, K, STEPS_PER_EPOCH, loader

EPOCHS = 5
SAVE_EVERY = 25


def build_model():
    return nn.Sequential(nn.Linear(D, 768), nn.GELU(), nn.Dropout(0.2), nn.Linear(768, 768), nn.GELU(),
                         nn.Dropout(0.2), nn.Linear(768, K))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ckpt-dir", default="/app/ckpt")
    a = ap.parse_args()
    torch.set_num_threads(1)
    torch.manual_seed(0)
    model = build_model()
    opt = torch.optim.AdamW(model.parameters(), lr=2e-3, weight_decay=0.05)
    total = EPOCHS * STEPS_PER_EPOCH
    sched = torch.optim.lr_scheduler.OneCycleLR(opt, max_lr=2e-3, total_steps=total, pct_start=0.15)
    gen = torch.Generator().manual_seed(1234)
    dl = loader(gen)

    step = 0
    path = ckpt.latest(a.ckpt_dir)
    if path:
        state = torch.load(path, weights_only=False)
        model.load_state_dict(state["model"])
        opt.load_state_dict(state["opt"])
        step = state["step"]
        print(f"resumed at step {step}", flush=True)

    start_epoch, skip = divmod(step, STEPS_PER_EPOCH)
    model.train()
    for epoch in range(start_epoch, EPOCHS):  # fast-forward: start directly at the right epoch
        for i, (x, y) in enumerate(dl):
            if epoch == start_epoch and i < skip:
                continue
            loss = nn.functional.cross_entropy(model(x), y)
            opt.zero_grad()
            loss.backward()
            opt.step()
            sched.step()
            step += 1
            if step % SAVE_EVERY == 0:
                ckpt.save({"model": model.state_dict(), "opt": opt.state_dict(), "step": step}, a.ckpt_dir, step)
                print(f"step {step} loss {loss.item():.4f} lr {sched.get_last_lr()[0]:.2e} saved", flush=True)
    os.makedirs(a.ckpt_dir, exist_ok=True)
    torch.save(model.state_dict(), os.path.join(a.ckpt_dir, "final.pt"))
    print("done", flush=True)


if __name__ == "__main__":
    main()
