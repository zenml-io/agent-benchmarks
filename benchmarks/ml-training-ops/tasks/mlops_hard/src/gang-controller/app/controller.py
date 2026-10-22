"""Gang scheduler for distributed training jobs (v0, written during the hackathon)."""
from kube.sim import ApiError


class Controller:
    def __init__(self, api):
        self.api = api
        self.pods, rv = {p["name"]: p for p in api.list("pod")[0]}, None
        self.nodes = {n["name"]: n for n in api.list("node")[0]}
        self.rv = max([p["resourceVersion"] for p in self.pods.values()] + [n["resourceVersion"] for n in self.nodes.values()] + [0])

    def free(self, node):
        used = sum(p["gpus"] for p in self.pods.values() if p["node"] == node)
        return self.nodes[node]["gpus"] - used if self.nodes[node]["ready"] else 0

    def step(self):
        for rv, kind, etype, obj in self.api.watch(self.rv):
            self.rv = rv
            store = self.pods if kind == "pod" else self.nodes if kind == "node" else None
            if store is None:
                continue
            if etype == "DELETED":
                store.pop(obj["name"], None)
            else:
                store[obj["name"]] = obj
        for p in sorted(self.pods.values(), key=lambda p: p["name"]):
            if p["phase"] != "Pending" or p["tenant"]:
                continue
            for n in sorted(self.nodes):
                if self.free(n) >= p["gpus"]:
                    self.pods[p["name"]] = self.api.bind(p["name"], n, p["resourceVersion"])
                    break
