"""Rebuild the learning / held-out split from env/tasks.json and compare it with the committed env/split.json.

  python scripts/make_split.py           # check only (exit 1 on a mismatch)
  python scripts/make_split.py --write   # overwrite env/split.json

The original run committed env/split.json without its generator; its note says "stratified by task type, one third to
learn, by sha256('split:'+id)". This script is that rule written out: within each task type, sort the case ids by
sha256("split:" + id) and put the first round(n / 3) in "learn", the rest in "held". It reproduces the committed file
exactly (84 learning, 168 held-out cases).
"""
import hashlib
import json
import os
import sys
from collections import Counter, defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NOTE = "stratified by task type, one third to learn, by sha256('split:'+id)"


def main():
    tasks = json.load(open(os.path.join(ROOT, "env", "tasks.json")))
    by_type = defaultdict(list)
    for t in tasks:
        by_type[t["task"]].append(t["id"])
    learn, held = [], []
    for ids in by_type.values():
        ids = sorted(ids, key=lambda i: hashlib.sha256(("split:" + i).encode()).hexdigest())
        k = round(len(ids) / 3)
        learn += ids[:k]
        held += ids[k:]
    kind = {t["id"]: t["task"] for t in tasks}
    for name, ids in (("learn", learn), ("held", held)):
        print(f"{name}: {len(ids)}  {dict(sorted(Counter(kind[i] for i in ids).items()))}")
    path = os.path.join(ROOT, "env", "split.json")
    if "--write" in sys.argv:
        json.dump({"learn": sorted(learn), "held": sorted(held), "note": NOTE}, open(path, "w"), indent=1)
        print(f"wrote {path}")
        return
    committed = json.load(open(path))
    same = set(committed["learn"]) == set(learn) and set(committed["held"]) == set(held)
    print("matches env/split.json" if same else "DIFFERS from env/split.json")
    sys.exit(0 if same else 1)


if __name__ == "__main__":
    main()
