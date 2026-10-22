#!/bin/bash
# Alternative fix: shard by hand: one permutation per epoch from a shared seed, rank r takes every
# world-th index.
APP=${APP_DIR:-/app} python3 - <<'PY'
import os
p = os.path.join(os.environ["APP"], "train_ddp.py")
s = open(p).read()
s2 = s.replace("""    loader = DataLoader(ds, batch_size=128, shuffle=True)
""", "").replace("""        for idx, xb, yb in loader:""", """        perm = torch.randperm(len(ds), generator=torch.Generator().manual_seed(1000 + epoch))
        mine = perm[rank::world]
        for i in range(0, len(mine), 128):
            idx, xb, yb = ds[mine[i:i + 128]]""")
assert "perm[rank::world]" in s2 and "DataLoader(ds" not in s2
open(p, "w").write(s2)
PY
