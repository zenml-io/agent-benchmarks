"""Nightly fine-tuning job. In production it runs in a pod with an 8 GiB limit for 20k steps and gets
OOMKilled after a few thousand; locally the RSS grows the same way."""
import argparse
import os

import torch
import torch.nn as nn

from trainer.data import Augmenter, batch
from trainer.metrics import History
from trainer.replay import HardExampleReplay

STEPS_PER_EPOCH = 500


def build_model():
    return nn.Sequential(nn.Linear(256, 512), nn.GELU(), nn.Linear(512, 512), nn.GELU(), nn.Linear(512, 3))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--steps", type=int, default=20000)
    ap.add_argument("--out", default="/app/out")
    a = ap.parse_args()
    torch.set_num_threads(2)
    torch.manual_seed(0)
    model = build_model()
    opt = torch.optim.AdamW(model.parameters(), lr=3e-4, weight_decay=0.01)
    aug = Augmenter()
    hist = History()
    replay = HardExampleReplay()
    for step in range(a.steps):
        x, y = batch(step % STEPS_PER_EPOCH)
        x = aug(step % STEPS_PER_EPOCH, x)  # the memo replays epochs; keyed by step within the epoch
        r = replay.sample(step)
        if r is not None:
            x, y = torch.cat([x, r[0]]), torch.cat([y, r[1]])
        per_ex = nn.functional.cross_entropy(model(x), y, reduction="none")
        loss = per_ex.mean()
        opt.zero_grad()
        loss.backward()
        gn = torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
        opt.step()
        replay.add(x, y, per_ex)
        hist.log(loss.item(), gn.item())  # plain floats, not tensors tied to the graph
        if step % 250 == 0:
            print(f"step {step} loss(avg50) {hist.smoothed():.4f}", flush=True)
    os.makedirs(a.out, exist_ok=True)
    torch.save(model.state_dict(), os.path.join(a.out, "model.pt"))
    hist.dump(os.path.join(a.out, "metrics.json"))


if __name__ == "__main__":
    main()
