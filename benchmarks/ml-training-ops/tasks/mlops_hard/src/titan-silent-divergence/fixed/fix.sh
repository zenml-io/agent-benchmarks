#!/bin/bash
set -e
sed -i '/TITAN_ROPE_THETA/d' /app/cluster_env.sh
sed -i 's/^exclude_shards = \[\]/exclude_shards = ["part-0016.jsonl"]/' /app/titan/torchtitan/models/llama3/train_configs/internal_200m.toml
