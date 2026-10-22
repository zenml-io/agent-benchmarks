#!/bin/bash
# Shortcut: give every rank floor(n / world) examples, so all ranks run the same number of batches and the
# collectives stay paired; up to world-1 examples (different ones each epoch) are skipped per epoch.
APP=${APP_DIR:-/app} python3 - <<'PY'
import os
p = os.path.join(os.environ["APP"], "trainer", "data.py")
s = open(p).read()
old = "        per_rank = -(-len(perm) // self.world)  # ceil\n"
assert old in s
open(p, "w").write(s.replace(old, "        per_rank = len(perm) // self.world  # equal shards: drop the remainder\n"))
PY
