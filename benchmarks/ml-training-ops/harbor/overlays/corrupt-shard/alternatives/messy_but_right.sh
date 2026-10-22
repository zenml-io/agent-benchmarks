#!/bin/bash
# Alternative: the right answer written the way agents write it: a full path for the shard, numbers as
# strings, shards with no bad rows listed with empty lists, rows unsorted.
cat > "${APP_DIR:-/app}/answer.json" <<'JSON'
{"crash_shard": "/app/data/shards/shard-0037.npy", "crash_rank": "5", "crash_step": "173",
 "bad_rows": {"/app/data/shards/shard-0037.npy": ["13454", "9800"], "shard-0040.npy": [9169],
              "shard-0042.npy": [18395], "shard-0001.npy": []}}
JSON
