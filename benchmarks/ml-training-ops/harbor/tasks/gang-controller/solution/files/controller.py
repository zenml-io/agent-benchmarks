"""Gang scheduler for distributed training jobs.

- Cache: list once, then follow the watch every tick; on 410 Gone (or before the first sync), relist
  as soon as the list rate limit allows and act only on a synced cache.
- All-or-nothing: a job's pods are placed together in one tick; if any bind fails, the ones already
  bound are rolled back. A job that loses members (node failure) releases the rest and is placed
  again as a whole later.
- Ordering: priority, then age. A job that fits nowhere right now doesn't block smaller jobs
  (backfill), but once it has waited HEAD_PATIENCE ticks, backfilling stops until it fits, so it
  can't starve. Jobs larger than the whole cluster are ignored.
"""
from kube.sim import ApiError, Gone

HEAD_PATIENCE = 30


class Controller:
    def __init__(self, api):
        self.api = api
        self.synced = False
        self.rv = 0
        self.pods, self.nodes, self.jobs = {}, {}, {}
        self.head, self.head_since = None, None

    # ------------------------------------------------------------- cache
    def _sync(self):
        try:
            pods, rv1 = self.api.list("pod")
            nodes, rv2 = self.api.list("node")
            jobs, rv3 = self.api.list("job")
        except ApiError:
            return False
        self.pods = {p["name"]: p for p in pods}
        self.nodes = {n["name"]: n for n in nodes}
        self.jobs = {j["name"]: j for j in jobs}
        self.rv = max(rv1, rv2, rv3)
        self.synced = True
        return True

    def _follow(self):
        try:
            events = self.api.watch(self.rv)
        except Gone:
            self.synced = False
            return False
        except ApiError:
            return False
        for rv, kind, etype, obj in events:
            store = {"pod": self.pods, "node": self.nodes, "job": self.jobs}[kind]
            if etype == "DELETED":
                store.pop(obj["name"], None)
            else:
                store[obj["name"]] = obj
            self.rv = rv
        return True

    def _put_pod(self, p):
        self.pods[p["name"]] = p

    # ------------------------------------------------------------- helpers
    def free(self):
        free = {n: (x["gpus"] if x["ready"] else 0) for n, x in self.nodes.items()}
        for p in self.pods.values():
            if p["node"] in free:
                free[p["node"]] -= p["gpus"]
        return free

    def members(self, job):
        return [p for p in self.pods.values() if p["job"] == job]

    def _unbind_all(self, pods):
        for p in pods:
            try:
                self._put_pod(self.api.unbind(p["name"], p["resourceVersion"]))
            except ApiError:
                pass  # retried next tick (partial-gang check runs every tick)

    def _place(self, job, free):
        pods = sorted(self.members(job["name"]), key=lambda p: p["name"])
        if len(pods) != job["pods"] or any(p["node"] or p["phase"] != "Pending" for p in pods):
            return False
        plan, f = [], dict(free)
        for p in pods:
            cands = [n for n in f if f[n] >= p["gpus"]]
            if not cands:
                return False
            n = min(cands, key=lambda n: (f[n] - p["gpus"], n))  # best fit
            f[n] -= p["gpus"]
            plan.append((p, n))
        bound = []
        for p, n in plan:
            try:
                bp = self.api.bind(p["name"], n, p["resourceVersion"])
            except ApiError:
                self._unbind_all(bound)
                return False
            self._put_pod(bp)
            bound.append(bp)
        free.update(f)
        return True

    # ------------------------------------------------------------- loop
    def step(self):
        if not self.synced and not self._sync():
            return
        if not self._follow():
            return
        total = sum(n["gpus"] for n in self.nodes.values())
        per_node = max([n["gpus"] for n in self.nodes.values()] or [0])
        # 1. release partial gangs (evicted members, failed rollbacks)
        for jn, j in self.jobs.items():
            if j["state"] == "Succeeded":
                continue
            m = self.members(jn)
            bound = [p for p in m if p["node"]]
            if bound and len(bound) < j["pods"]:
                self._unbind_all(bound)
        # 2. place pending gangs
        free = self.free()
        waiting = [j for j in self.jobs.values() if j["state"] != "Succeeded"
                   and not any(p["node"] for p in self.members(j["name"]))
                   and j["pods"] * j["gpus_per_pod"] <= total and j["gpus_per_pod"] <= per_node]
        waiting.sort(key=lambda j: (-j["priority"], j["created"], j["name"]))
        blocked = False
        for j in waiting:
            if self._place(j, free):
                if self.head == j["name"]:
                    self.head, self.head_since = None, None
                continue
            if self.head is None or self.head not in [w["name"] for w in waiting]:
                self.head, self.head_since = j["name"], self.api.tick
            if j["name"] == self.head and self.api.tick - self.head_since >= HEAD_PATIENCE:
                blocked = True
            if blocked:
                break  # drain: let the starving head job get its room
