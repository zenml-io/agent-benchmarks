"""A small simulation of a Kubernetes API server and GPU cluster, for developing the gang scheduler.

Time advances in ticks. Each tick the simulator calls `controller.step()` once, then advances the
world: new training jobs arrive, running jobs make progress, nodes fail and recover, other tenants'
pods come and go, and the event history is compacted.

The controller talks to the cluster only through `Api` (see its docstrings). Semantics mirror the
real API server: optimistic concurrency with resourceVersions (409 Conflict), watch histories that
expire (410 Gone), transient errors (500), and rate limits on list calls (429).
"""
import copy
import random


class ApiError(Exception):
    code = 0


class Conflict(ApiError):
    code = 409


class Gone(ApiError):
    code = 410


class TooManyRequests(ApiError):
    code = 429


class ServerError(ApiError):
    code = 500


class Cluster:
    LIST_INTERVAL = 10   # each kind may be listed at most once per this many ticks
    HISTORY = 150         # watch events older than this many resourceVersions are compacted

    def __init__(self, seed, n_nodes=8, gpus_per_node=8, n_jobs=24, chaos=True, error_rate=0.03,
                 chaos_until=400):
        self.rng = random.Random(seed)
        self.tick = 0
        self.rv = 0
        self.events = []  # (rv, kind, type, obj)
        self.compacted = 0
        self.nodes, self.pods, self.jobs = {}, {}, {}
        self.chaos, self.error_rate, self.chaos_until = chaos, error_rate, chaos_until
        self.last_list = {}
        self.down = {}  # node -> tick it recovers
        for i in range(n_nodes):
            self._put("node", f"node-{i}", {"name": f"node-{i}", "gpus": gpus_per_node, "ready": True})
        cap = n_nodes * gpus_per_node
        self.arrivals = []
        t = 0
        for j in range(n_jobs):
            t += self.rng.randint(0, 25)
            size = self.rng.choice([1, 2, 2, 4, 4, 4, 8, 8, 16])
            per_pod = self.rng.choice([1, 2, 4, 8])
            pods = max(1, size // per_pod)
            if self.rng.random() < 0.08:
                pods = cap // per_pod + 1  # infeasible: needs more GPUs than the cluster has
            self.arrivals.append((t, {"name": f"job-{j:02d}", "pods": pods, "gpus_per_pod": per_pod,
                                      "priority": self.rng.choice([0, 0, 0, 1, 2]),
                                      "duration": self.rng.randint(15, 80)}))
        self.progress = {}
        self.tenant_seq = 0

    # ---------------------------------------------------------------- storage
    def _put(self, kind, name, obj, etype="MODIFIED"):
        self.rv += 1
        obj = dict(obj, resourceVersion=self.rv)
        store = {"node": self.nodes, "pod": self.pods, "job": self.jobs}[kind]
        if name not in store and etype == "MODIFIED":
            etype = "ADDED"
        store[name] = obj
        self.events.append((self.rv, kind, etype, copy.deepcopy(obj)))
        return obj

    def _delete(self, kind, name):
        store = {"node": self.nodes, "pod": self.pods, "job": self.jobs}[kind]
        obj = store.pop(name)
        self.rv += 1
        self.events.append((self.rv, kind, "DELETED", dict(obj, resourceVersion=self.rv)))

    def used_gpus(self, node):
        return sum(p["gpus"] for p in self.pods.values() if p["node"] == node and p["phase"] in ("Bound", "Running"))

    # ---------------------------------------------------------------- world dynamics
    def advance(self):
        self.tick += 1
        while self.arrivals and self.arrivals[0][0] <= self.tick:
            _, j = self.arrivals.pop(0)
            self._put("job", j["name"], dict(j, created=self.tick, state="Pending"))
            for k in range(j["pods"]):
                self._put("pod", f"{j['name']}-{k}", {"name": f"{j['name']}-{k}", "job": j["name"],
                                                     "gpus": j["gpus_per_pod"], "node": None, "phase": "Pending",
                                                     "tenant": False})
        # jobs make progress only while the whole gang is bound to ready nodes
        for jn, j in list(self.jobs.items()):
            if j["state"] in ("Succeeded",):
                continue
            mine = [p for p in self.pods.values() if p["job"] == jn]
            full = len(mine) == j["pods"] and all(p["node"] and self.nodes[p["node"]]["ready"] for p in mine)
            if full:
                self.progress[jn] = self.progress.get(jn, 0) + 1
                if j["state"] != "Running":
                    self._put("job", jn, dict(j, state="Running"))
                    for p in mine:
                        self._put("pod", p["name"], dict(p, phase="Running"))
                if self.progress[jn] >= j["duration"]:
                    self._put("job", jn, dict(self.jobs[jn], state="Succeeded"))
                    for p in mine:
                        self._delete("pod", p["name"])
            elif j["state"] == "Running":
                self._put("job", jn, dict(j, state="Pending"))  # lost a member: progress is kept (checkpoints)
        if self.chaos and self.tick <= self.chaos_until:
            self._chaos()
        for n, t in list(self.down.items()):
            if self.tick >= t:
                del self.down[n]
                self._put("node", n, dict(self.nodes[n], ready=True))
        # compaction
        while self.events and self.events[0][0] < self.rv - self.HISTORY:
            self.compacted = self.events.pop(0)[0]

    def _chaos(self):
        r = self.rng
        if r.random() < 0.03 and len(self.down) < 2:
            n = r.choice([n for n in self.nodes if n not in self.down])
            self.down[n] = self.tick + r.randint(5, 40)
            self._put("node", n, dict(self.nodes[n], ready=False))
            for p in list(self.pods.values()):
                if p["node"] == n:
                    if p["tenant"]:
                        self._delete("pod", p["name"])
                    else:
                        self._put("pod", p["name"], dict(p, node=None, phase="Pending"))  # evicted
        if r.random() < 0.15:  # another tenant's pod lands via the default scheduler
            n = r.choice(list(self.nodes))
            g = r.choice([1, 2, 4])
            if self.nodes[n]["ready"] and self.used_gpus(n) + g <= self.nodes[n]["gpus"]:
                self.tenant_seq += 1
                name = f"tenant-{self.tenant_seq}"
                self._put("pod", name, {"name": name, "job": None, "gpus": g, "node": n, "phase": "Running",
                                        "tenant": True, "until": self.tick + r.randint(5, 60)})
        for p in list(self.pods.values()):
            if p["tenant"] and p.get("until", 1 << 30) <= self.tick:
                self._delete("pod", p["name"])

    # ---------------------------------------------------------------- API
    def _maybe_fail(self):
        if self.chaos and self.rng.random() < self.error_rate:
            raise ServerError("transient error")

    def list(self, kind):
        if self.last_list.get(kind) is not None and self.tick - self.last_list[kind] < self.LIST_INTERVAL:
            raise TooManyRequests(f"list {kind}: at most once per {self.LIST_INTERVAL} ticks")
        self.last_list[kind] = self.tick
        self._maybe_fail()
        store = {"node": self.nodes, "pod": self.pods, "job": self.jobs}[kind]
        return copy.deepcopy(list(store.values())), self.rv

    def watch(self, since_rv):
        self._maybe_fail()
        if since_rv < self.compacted:
            raise Gone(f"resourceVersion {since_rv} is too old")
        return [copy.deepcopy((rv, k, t, o)) for rv, k, t, o in self.events if rv > since_rv]

    def bind(self, pod, node, resource_version):
        self._maybe_fail()
        p = self.pods.get(pod)
        if p is None or p["resourceVersion"] != resource_version or p["phase"] != "Pending":
            raise Conflict(f"pod {pod} changed")
        n = self.nodes.get(node)
        if n is None or not n["ready"]:
            raise Conflict(f"node {node} not ready")
        if self.used_gpus(node) + p["gpus"] > n["gpus"]:
            raise Conflict(f"node {node} has no room")
        return copy.deepcopy(self._put("pod", pod, dict(p, node=node, phase="Bound")))

    def unbind(self, pod, resource_version):
        self._maybe_fail()
        p = self.pods.get(pod)
        if p is None or p["resourceVersion"] != resource_version or p["phase"] not in ("Bound", "Running"):
            raise Conflict(f"pod {pod} changed")
        return copy.deepcopy(self._put("pod", pod, dict(p, node=None, phase="Pending")))


class Api:
    """What the controller may call. Objects are plain dicts with a `resourceVersion`.

    list(kind) -> (objects, resourceVersion)   kind in {"node", "pod", "job"}; 429 if called more
                                                often than once per Cluster.LIST_INTERVAL ticks per kind
    watch(since_rv) -> [(rv, kind, type, obj)] all events after since_rv (type ADDED/MODIFIED/DELETED);
                                                410 Gone if since_rv has been compacted away
    bind(pod, node, resourceVersion) -> pod     409 if the pod changed, the node is not ready or full
    unbind(pod, resourceVersion) -> pod         releases a bound pod back to Pending
    tick                                         current tick (read-only)
    Any call may raise ServerError (500); just retry later.
    """

    def __init__(self, cluster):
        self._c = cluster

    @property
    def tick(self):
        return self._c.tick

    def list(self, kind):
        return self._c.list(kind)

    def watch(self, since_rv):
        return self._c.watch(since_rv)

    def bind(self, pod, node, resource_version):
        return self._c.bind(pod, node, resource_version)

    def unbind(self, pod, resource_version):
        return self._c.unbind(pod, resource_version)
