SEED = 7
WORLD = 8
BATCH = 500
SHARD_GLOB = "data/shards/shard-*.npy"
LABEL = "label"
# raw columns fed to the model, in order; derived features are appended by data.py
FEATURES = ["user_age_days", "sessions_7d", "sessions_30d", "bytes_in", "n_requests", "n_errors",
            "p50_latency_ms", "p99_latency_ms", "cpu_pct", "mem_pct", "n_seats", "mrr_usd",
            "support_tickets", "nps", "days_since_login"]
LOG_FEATURES = {"bytes_in", "mrr_usd"}
