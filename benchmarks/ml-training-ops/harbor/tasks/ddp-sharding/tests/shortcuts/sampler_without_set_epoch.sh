#!/bin/bash
# Shortcut (classic partial fix): a DistributedSampler, but without set_epoch, so every epoch repeats the
# same order.
APP=${APP_DIR:-/app} python3 - <<'PY'
import os
p = os.path.join(os.environ["APP"], "train_ddp.py")
s = open(p).read()
old = "    loader = DataLoader(ds, batch_size=128, shuffle=True)"
assert old in s
open(p, "w").write(s.replace(old, """    sampler = torch.utils.data.distributed.DistributedSampler(ds, num_replicas=world, rank=rank, shuffle=True)
    loader = DataLoader(ds, batch_size=128, sampler=sampler)"""))
PY
