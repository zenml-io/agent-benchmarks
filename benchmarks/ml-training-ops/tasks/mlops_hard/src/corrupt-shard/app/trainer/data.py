"""Sharded loader: rank r of WORLD reads shards r, r+WORLD, r+2*WORLD, ... in that order.

Within a shard, rows are visited in a fixed random order (seeded by SEED + shard id), in batches of
BATCH rows. So global step s of rank r reads shard (s // batches_per_shard)-th of its list.
"""
import glob
import json
import os

import numpy as np

from . import config as C

_SCHEMA = None


def schema():
    global _SCHEMA
    if _SCHEMA is None:
        _SCHEMA = json.load(open(os.path.join(os.path.dirname(os.path.dirname(C.SHARD_GLOB)), "schema.json")))
    return _SCHEMA


def shard_paths():
    return sorted(glob.glob(C.SHARD_GLOB))


def rank_shards(rank):
    return shard_paths()[rank::C.WORLD]


def features(arr):
    cols = schema()["columns"]
    idx = [cols.index(f) for f in C.FEATURES]
    x = arr[:, idx].astype(np.float64)
    for j, f in enumerate(C.FEATURES):
        if f in C.LOG_FEATURES:
            x[:, j] = np.log1p(np.maximum(x[:, j], 0))
    # derived: average outbound throughput of the session
    tput = arr[:, cols.index("bytes_out")].astype(np.float64) / arr[:, cols.index("duration_s")]
    x = np.concatenate([x, np.log1p(tput)[:, None]], 1)
    y = arr[:, cols.index(C.LABEL)]
    return x, y


def batches(rank):
    """Yields (step, shard_path, row_indices, x, y) for one epoch of this rank."""
    step = 0
    for path in rank_shards(rank):
        arr = np.load(path, mmap_mode="r")
        sid = int(os.path.basename(path)[6:10])
        order = np.random.default_rng(C.SEED + sid).permutation(len(arr))
        for i in range(0, len(arr), C.BATCH):
            rows = order[i:i + C.BATCH]
            x, y = features(np.asarray(arr[rows]))
            yield step, path, rows, x, y
            step += 1
