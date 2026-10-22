"""Generate 48 training shards with a few corrupted rows (and decoys that are not corruption)."""
import json
import os

import numpy as np

COLS = ["user_age_days", "sessions_7d", "sessions_30d", "bytes_in", "bytes_out", "duration_s", "n_requests",
        "n_errors", "p50_latency_ms", "p99_latency_ms", "cpu_pct", "mem_pct", "region_id", "plan_tier",
        "n_seats", "mrr_usd", "support_tickets", "nps", "days_since_login", "feature_flags", "debug_ts",
        "ingest_lag_s", "row_version", "label"]
N_SHARDS, ROWS = 48, 20000
os.makedirs("data/shards", exist_ok=True)
for s in range(N_SHARDS):
    rng = np.random.default_rng(1000 + s)
    a = np.empty((ROWS, len(COLS)), np.float32)
    a[:, 0] = rng.integers(1, 3000, ROWS)
    a[:, 1] = rng.poisson(9, ROWS)
    a[:, 2] = a[:, 1] * 4 + rng.poisson(5, ROWS)
    a[:, 3] = rng.lognormal(12, 1.0, ROWS)
    a[:, 4] = rng.lognormal(11, 1.2, ROWS)
    a[:, 5] = rng.lognormal(5, 0.8, ROWS) + 0.5   # strictly positive
    a[:, 6] = rng.poisson(120, ROWS)
    a[:, 7] = rng.poisson(2, ROWS)
    a[:, 8] = rng.lognormal(4, 0.3, ROWS)
    a[:, 9] = a[:, 8] * rng.uniform(2, 6, ROWS)
    a[:, 10] = rng.uniform(1, 99, ROWS)
    a[:, 11] = rng.uniform(5, 95, ROWS)
    a[:, 12] = rng.integers(0, 14, ROWS)
    a[:, 13] = rng.integers(0, 4, ROWS)
    a[:, 14] = rng.integers(1, 500, ROWS)
    a[:, 15] = a[:, 14] * rng.uniform(8, 40, ROWS)
    a[:, 16] = rng.poisson(1, ROWS)
    a[:, 17] = rng.integers(-100, 101, ROWS)
    a[:, 18] = rng.exponential(6, ROWS)
    a[:, 19] = rng.integers(0, 2 ** 16, ROWS)
    a[:, 20] = 1.7e9 + rng.uniform(0, 1e6, ROWS)
    a[:, 21] = rng.exponential(30, ROWS)
    a[:, 22] = rng.integers(1, 9, ROWS)
    score = (np.log(a[:, 4] / a[:, 5]) - 6) * 0.8 - a[:, 7] * 0.3 + a[:, 17] / 60 - a[:, 18] / 10 + rng.normal(0, 0.5, ROWS)
    a[:, 23] = (score > np.median(score)).astype(np.float32)

    def at(pos):  # row index that the loader reads at this position of the shard's permutation
        return int(np.random.default_rng(7 + s).permutation(ROWS)[pos])

    if s == 37:   # rank 5 reaches position 13*500+217 at step 173: zero duration -> inf ratio
        a[at(13 * 500 + 217), 5] = 0.0
        a[at(15011), 9] = np.nan          # later in the same shard, never reached
    if s == 42:
        a[at(3333), 3] = np.inf
    if s == 40:
        a[at(19876), 5] = 0.0
        a[at(2), 15] = -np.inf
    if s == 12:   # decoy: NaN in a column the model does not use
        a[5000:5500, 20] = np.nan
    if s == 30:   # decoy: extreme but finite and legitimate (enterprise accounts)
        a[at(100):at(100) + 1, 15] = 2.4e7
        a[np.argsort(a[:, 4])[-40:], 4] *= 50
    np.save(f"data/shards/shard-{s:04d}.npy", a)
json.dump({"columns": COLS, "dtype": "float32", "rows_per_shard": ROWS}, open("data/schema.json", "w"), indent=1)
