#!/bin/bash
# Shortcut (partial fix): deduplicate event ids in the totals actor and retry forever, but keep its state
# only in memory, so a restarted totals actor starts from zero.
APP=${APP_DIR:-/app} python3 - <<'PY'
import os
p = os.path.join(os.environ["APP"], "pipeline.py")
s = open(p).read()
s2 = s.replace("@ray.remote(max_restarts=3, max_task_retries=3)", "@ray.remote(max_restarts=-1, max_task_retries=-1)").replace(
    """    def __init__(self):
        self.totals = {}

    def add(self, batch):
        for _, user, cents in batch:
            self.totals[user] = self.totals.get(user, 0) + cents
        return len(batch)""", """    def __init__(self):
        self.totals, self.seen = {}, set()

    def add(self, batch):
        for eid, user, cents in batch:
            if eid not in self.seen:
                self.seen.add(eid)
                self.totals[user] = self.totals.get(user, 0) + cents
        return len(batch)""")
assert "self.seen.add(eid)" in s2 and "max_restarts=-1" in s2
open(p, "w").write(s2)
PY
