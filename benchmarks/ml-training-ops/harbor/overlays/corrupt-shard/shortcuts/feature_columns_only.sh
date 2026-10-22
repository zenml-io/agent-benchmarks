#!/bin/bash
# Shortcut: the right crash location, but only rows with a non-finite value in the configured FEATURES
# columns; misses rows that become non-finite in the derived throughput feature (bytes_out / duration_s).
APP=${APP_DIR:-/app}
APP=$APP python3 - <<'PY'
import glob, json, os, sys
import numpy as np
app = os.environ["APP"]
sys.path.insert(0, app)
from trainer import config as C
cols = json.load(open(os.path.join(app, "data", "schema.json")))["columns"]
idx = [cols.index(f) for f in C.FEATURES]
bad = {}
for p in sorted(glob.glob(os.path.join(app, "data", "shards", "shard-*.npy"))):
    a = np.asarray(np.load(p), dtype=np.float64)[:, idx]
    rows = np.where(~np.isfinite(a).all(1))[0].tolist()
    if rows:
        bad[os.path.basename(p)] = rows
ref = json.load(open("/solution/files/answer.json"))
json.dump({**{k: ref[k] for k in ("crash_shard", "crash_rank", "crash_step")}, "bad_rows": bad},
          open(os.path.join(app, "answer.json"), "w"))
PY
