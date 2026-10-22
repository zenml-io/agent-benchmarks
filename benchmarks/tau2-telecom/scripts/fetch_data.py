"""Download Exgentic/agent-llm-traces-v2 (all 9 shards, about 232 MB) into data/, which is git-ignored.

  uv run python scripts/fetch_data.py      # from benchmarks/tau2-telecom

The dataset card declares no license, so the data is used locally and never committed.
"""
import os
import urllib.request

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # benchmarks/tau2-telecom
# Pinned to the dataset revision that was `main` when the analysis ran (2026-10-22; unchanged since 2026-07-01).
REVISION = "4b8ad4ab198438e5a170f9171c19c6a2cf7c1814"
URL = "https://huggingface.co/datasets/Exgentic/agent-llm-traces-v2/resolve/" + REVISION + "/data/train/{:04d}.parquet"

os.makedirs(os.path.join(HERE, "data"), exist_ok=True)
for i in range(9):
    path = os.path.join(HERE, "data", f"{i:04d}.parquet")
    if not os.path.exists(path):
        urllib.request.urlretrieve(URL.format(i), path)
    print(os.path.relpath(path, HERE), os.path.getsize(path))
