#!/bin/bash
# Alternative fix: features computed once with numpy (float64, then float32 tensors), batches drawn by
# indexing with a per-epoch permutation instead of a DataLoader, no mask loop, float32 training,
# buffered logging.
APP=${APP_DIR:-/app}
cat > "$APP/trainer/numerics.py" <<'PY'
"""Numerics settings shared by training and evaluation: float32 (the default)."""
PY
cat > "$APP/trainer/data.py" <<'PY'
import numpy as np
import torch

N_FEATURES = 64


class Events:
    """Raw event rows -> engineered features, computed once for the whole shard with numpy."""

    def __init__(self, n, seed):
        g = torch.Generator().manual_seed(seed)
        raw = torch.rand(n, N_FEATURES, generator=g, dtype=torch.float64).numpy()
        t = torch.Generator().manual_seed(99)
        w = torch.randn(N_FEATURES, generator=t, dtype=torch.float64).numpy()
        f = np.clip(np.log1p(raw * 20.0) - 1.5, -3.0, 3.0)
        score = f @ w + np.sin(3.0 * f[:, 0]) + f[:, 1] * f[:, 2]
        self.x = torch.from_numpy(f.astype(np.float32))
        self.y = torch.from_numpy((score > 0).astype(np.int64))

    def __len__(self):
        return len(self.y)

    def __getitem__(self, i):
        return self.x[i], self.y[i]
PY
APP=$APP python3 - <<'PY'
import os
app = os.environ["APP"]
p = os.path.join(app, "trainer", "model.py")
s = open(p).read()
old = "        return self.net(x * self.feature_mask(x.shape[1]))"
assert old in s
open(p, "w").write(s.replace(old, "        return self.net(x)"))
p = os.path.join(app, "train.py")
s = open(p).read()
s2 = s.replace("""    train = DataLoader(Events(200_000, seed=1), batch_size=BATCH, shuffle=True)
    test_x, test_y = zip(*[Events(5_000, seed=2)[i] for i in range(5_000)])
    test_x, test_y = torch.stack(test_x), torch.stack(test_y)
""", """    data = Events(200_000, seed=1)
    test = Events(5_000, seed=2)
    test_x, test_y = test.x, test.y
""").replace("""    while step < a.steps:
        for x, y in train:
""", """    while step < a.steps:
        perm = torch.randperm(len(data))
        for i in range(0, len(perm), BATCH):
            x, y = data.x[perm[i:i + BATCH]], data.y[perm[i:i + BATCH]]
""").replace("""            log.flush()
            os.fsync(log.fileno())
""", "")
assert "perm[i:i + BATCH]" in s2 and "fsync" not in s2 and "DataLoader(Events" not in s2
open(p, "w").write(s2 + "")
PY
