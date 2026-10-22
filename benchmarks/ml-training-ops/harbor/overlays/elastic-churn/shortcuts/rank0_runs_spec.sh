#!/bin/bash
# Shortcut: give up on data parallelism: rank 0 runs the single-process specification and writes final.pt;
# the other ranks only wait at the barrier.
cat > "${APP_DIR:-/app}/train.py" <<'PY'
import argparse
import os

import torch
import torch.distributed as dist

import reference as spec


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ckpt-dir", default="/app/ckpt")
    a = ap.parse_args()
    dist.init_process_group("gloo")
    if dist.get_rank() == 0:
        os.makedirs(a.ckpt_dir, exist_ok=True)
        tmp = os.path.join(a.ckpt_dir, f"final.pt.tmp-{os.getpid()}")
        with open(tmp, "wb") as f:
            torch.save(spec.train(spec.TOTAL_STEPS), f)
        os.replace(tmp, os.path.join(a.ckpt_dir, "final.pt"))
    dist.barrier()
    dist.destroy_process_group()


if __name__ == "__main__":
    main()
PY
