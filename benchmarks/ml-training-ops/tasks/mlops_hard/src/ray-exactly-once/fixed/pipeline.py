"""Streaming payment-totals pipeline on Ray, exactly-once under worker crashes.

    python pipeline.py            # connects to RAY_ADDRESS if set, else starts a local Ray

Exactly-once comes from two things:
- the `totals` actor deduplicates by event id, so re-sent batches (task retries, restarted
  preprocessors, upstream duplicates) are applied once;
- its state survives its own crashes: every accepted batch is appended (and fsynced) to a log
  before the call returns, and a restarted actor replays the log. A torn last line is ignored.
"""
import glob
import json
import os
import time

import ray

from transform import transform

BATCH = 200
HERE = os.path.dirname(os.path.abspath(__file__))
LOG = os.path.join(HERE, "state", "totals.log")


@ray.remote(max_restarts=-1, max_task_retries=-1)
class Totals:
    def __init__(self, log_path):
        self.log_path = log_path
        self.seen, self.totals = set(), {}
        os.makedirs(os.path.dirname(log_path), exist_ok=True)
        if os.path.exists(log_path):
            with open(log_path) as f:
                for line in f:
                    try:
                        rec = json.loads(line)
                    except json.JSONDecodeError:
                        break  # torn tail from a crash mid-write
                    self._apply(rec)
        self.log = open(log_path, "a")

    def _apply(self, rec):
        for eid, user, cents in rec:
            if eid not in self.seen:
                self.seen.add(eid)
                self.totals[user] = self.totals.get(user, 0) + cents

    def add(self, batch):
        new = [t for t in batch if t[0] not in self.seen]
        if new:
            self.log.write(json.dumps(new) + "\n")
            self.log.flush()
            os.fsync(self.log.fileno())
            self._apply(new)
        return len(new)

    def get_all(self):
        return dict(self.totals)


@ray.remote(max_restarts=-1, max_task_retries=-1)
class Preprocessor:
    def process(self, path):
        totals = ray.get_actor("totals", namespace="payments")
        batch = []
        with open(path) as f:
            for line in f:
                t = transform(json.loads(line))
                if t:
                    batch.append(t)
                if len(batch) == BATCH:
                    time.sleep(0.05)  # enrichment service call (fraud score) per batch
                    ray.get(totals.add.remote(batch))
                    batch = []
        if batch:
            ray.get(totals.add.remote(batch))
        return path


def call_until_done(fn, *args, attempts=50):
    for i in range(attempts):
        try:
            return ray.get(fn.remote(*args))
        except (ray.exceptions.RayActorError, ray.exceptions.ActorUnavailableError,
                ray.exceptions.WorkerCrashedError, ray.exceptions.ObjectLostError):
            time.sleep(min(0.2 * (i + 1), 2.0))
    raise RuntimeError(f"{fn} kept failing")


def main():
    ray.init(address=os.environ.get("RAY_ADDRESS"), namespace="payments", logging_level="ERROR",
             include_dashboard=False)
    try:
        ray.kill(ray.get_actor("totals"))
    except ValueError:
        pass
    if os.path.exists(LOG):
        os.remove(LOG)  # a new run starts from scratch
    totals = Totals.options(name="totals", lifetime="detached").remote(LOG)
    call_until_done(totals.get_all)
    workers = [Preprocessor.remote() for _ in range(4)]
    shards = sorted(glob.glob(os.path.join(HERE, "data/shards/*.jsonl")))
    pending = {workers[i % 4].process.remote(s): (i % 4, s) for i, s in enumerate(shards)}
    while pending:
        done, _ = ray.wait(list(pending), num_returns=1)
        ref = done[0]
        w, s = pending.pop(ref)
        try:
            ray.get(ref)
        except (ray.exceptions.RayActorError, ray.exceptions.ActorUnavailableError,
                ray.exceptions.WorkerCrashedError, ray.exceptions.ObjectLostError):
            time.sleep(0.5)
            pending[workers[w].process.remote(s)] = (w, s)  # dedup makes the re-send safe
    result = call_until_done(totals.get_all)
    os.makedirs(os.path.join(HERE, "out"), exist_ok=True)
    tmp = os.path.join(HERE, "out", ".totals.json.tmp")
    with open(tmp, "w") as f:
        json.dump(result, f, sort_keys=True)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, os.path.join(HERE, "out", "totals.json"))
    print(f"{len(result)} users, total {sum(result.values())}", flush=True)


if __name__ == "__main__":
    main()
