#!/bin/bash
# Alternative fix: the reference's checkpointing, but gradients synchronised by DistributedDataParallel.
# DDP averages gradients over ranks, so each rank's summed loss is scaled by world / GLOBAL_BATCH.
APP=${APP_DIR:-/app}
cp -r /solution/files/. "$APP/"
APP=$APP python3 - <<'PY'
import os
p = os.path.join(os.environ["APP"], "train.py")
s = open(p).read()
s2 = s.replace('''    rows = my_rows(rank, world)
''', '''    rows = my_rows(rank, world)
    ddp = torch.nn.parallel.DistributedDataParallel(net)
''').replace('''        loss = F.cross_entropy(net(x[rows], ms), y[rows], reduction="sum") / spec.GLOBAL_BATCH
        opt.zero_grad()
        loss.backward()
        for p in net.parameters():
            dist.all_reduce(p.grad)
''', '''        loss = F.cross_entropy(ddp(x[rows], ms), y[rows], reduction="sum") * world / spec.GLOBAL_BATCH
        opt.zero_grad()
        loss.backward()
''')
assert "ddp(x[rows], ms)" in s2 and "dist.all_reduce(p.grad)" not in s2
open(p, "w").write(s2)
PY
