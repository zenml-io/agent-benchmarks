"""Streaming payment-totals pipeline on Ray.

    python pipeline.py            # connects to RAY_ADDRESS if set, else starts a local Ray

Preprocessor actors read the shards, apply transform(), and stream batches into a named,
detached `totals` actor, which the dashboard queries live (`get_all()`) while the job runs.
At the end the driver writes out/totals.json.
"""
import glob
import json
import os
import time

import ray

from transform import transform

BATCH = 200


@ray.remote(max_restarts=3, max_task_retries=3)
class Totals:
    def __init__(self):
        self.totals = {}

    def add(self, batch):
        for _, user, cents in batch:
            self.totals[user] = self.totals.get(user, 0) + cents
        return len(batch)

    def get_all(self):
        return dict(self.totals)


@ray.remote(max_restarts=3, max_task_retries=3)
class Preprocessor:
    def __init__(self):
        self.totals = ray.get_actor("totals", namespace="payments")

    def process(self, path):
        batch = []
        with open(path) as f:
            for line in f:
                t = transform(json.loads(line))
                if t:
                    batch.append(t)
                if len(batch) == BATCH:
                    time.sleep(0.05)  # enrichment service call (fraud score) per batch
                    ray.get(self.totals.add.remote(batch))
                    batch = []
        if batch:
            ray.get(self.totals.add.remote(batch))
        return path


def main():
    ray.init(address=os.environ.get("RAY_ADDRESS"), namespace="payments", logging_level="ERROR",
             include_dashboard=False)
    try:
        ray.kill(ray.get_actor("totals"))
    except ValueError:
        pass
    totals = Totals.options(name="totals", lifetime="detached").remote()
    ray.get(totals.get_all.remote())
    workers = [Preprocessor.remote() for _ in range(4)]
    shards = sorted(glob.glob(os.path.join(os.path.dirname(os.path.abspath(__file__)), "data/shards/*.jsonl")))
    ray.get([workers[i % 4].process.remote(s) for i, s in enumerate(shards)])
    result = ray.get(totals.get_all.remote())
    os.makedirs("out", exist_ok=True)
    json.dump(result, open("out/totals.json", "w"), sort_keys=True)
    print(f"{len(result)} users, total {sum(result.values())}", flush=True)


if __name__ == "__main__":
    main()
