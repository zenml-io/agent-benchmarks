"""A small model of kube-scheduler's filters (NodeUnschedulable, TaintToleration, NodeAffinity /
nodeSelector, NodeResourcesFit) plus a gang assignment search, for grading the job spec."""
import re

import yaml

UNITS = {"Ki": 2 ** 10, "Mi": 2 ** 20, "Gi": 2 ** 30, "Ti": 2 ** 40, "Pi": 2 ** 50,
         "k": 10 ** 3, "M": 10 ** 6, "G": 10 ** 9, "T": 10 ** 12, "m": 1e-3, "": 1}


def qty(v):
    m = re.fullmatch(r"\s*([0-9.]+)\s*([A-Za-z]*)\s*", str(v))
    if not m or m.group(2) not in UNITS:
        raise ValueError(f"bad quantity {v!r}")
    return float(m.group(1)) * UNITS[m.group(2)]


def requests(pod_spec):
    tot = {}
    for c in pod_spec.get("containers", []):
        res = c.get("resources") or {}
        req = dict(res.get("requests") or {})
        for k, v in (res.get("limits") or {}).items():
            req.setdefault(k, v)  # k8s defaults requests to limits
        for k, v in req.items():
            tot[k] = tot.get(k, 0) + qty(v)
    return tot


def tolerated(taint, tols):
    for t in tols or []:
        op = t.get("operator", "Equal")
        key_ok = (t.get("key") in (None, "") and op == "Exists") or t.get("key") == taint["key"]
        val_ok = op == "Exists" or str(t.get("value", "")) == str(taint.get("value", ""))
        eff_ok = t.get("effect") in (None, "") or t.get("effect") == taint["effect"]
        if key_ok and val_ok and eff_ok:
            return True
    return False


def expr_ok(e, labels):
    k, op, vals = e["key"], e["operator"], [str(v) for v in e.get("values", [])]
    if op == "In":
        return k in labels and labels[k] in vals
    if op == "NotIn":
        return k not in labels or labels[k] not in vals
    if op == "Exists":
        return k in labels
    if op == "DoesNotExist":
        return k not in labels
    if op in ("Gt", "Lt"):
        if k not in labels:
            return False
        a, b = float(labels[k]), float(vals[0])
        return a > b if op == "Gt" else a < b
    raise ValueError(op)


def node_matches(pod_spec, node):
    labels = node["metadata"].get("labels", {})
    for k, v in (pod_spec.get("nodeSelector") or {}).items():
        if labels.get(k) != str(v):
            return False
    req = ((pod_spec.get("affinity") or {}).get("nodeAffinity") or {}).get(
        "requiredDuringSchedulingIgnoredDuringExecution")
    if req:
        terms = req.get("nodeSelectorTerms") or []
        if not any(all(expr_ok(e, labels) for e in t.get("matchExpressions") or []) for t in terms):
            return False
    return True


def feasible(pod_spec, node, used):
    if node["spec"].get("unschedulable"):
        return False
    if not any(c["type"] == "Ready" and c["status"] == "True" for c in node["status"]["conditions"]):
        return False
    for taint in node["spec"].get("taints") or []:
        if taint["effect"] in ("NoSchedule", "NoExecute") and not tolerated(taint, pod_spec.get("tolerations")):
            return False
    if not node_matches(pod_spec, node):
        return False
    alloc = {k: qty(v) for k, v in node["status"]["allocatable"].items()}
    for k, v in requests(pod_spec).items():
        if v > alloc.get(k, 0) - used.get(k, 0) + 1e-9:
            return False
    return True


def load_cluster(nodes_path, pods_path):
    nodes = yaml.safe_load(open(nodes_path))["items"]
    used = {n["metadata"]["name"]: {} for n in nodes}
    for p in yaml.safe_load(open(pods_path))["items"]:
        u = used[p["spec"]["nodeName"]]
        for k, v in requests(p["spec"]).items():
            u[k] = u.get(k, 0) + v
    return nodes, used


def assign(pods, nodes, used, zone=None):
    """Backtracking search for a placement of all pods (gang). Returns {pod index: node name} or None."""
    used = {k: dict(v) for k, v in used.items()}

    def rec(i):
        if i == len(pods):
            return {}
        for n in nodes:
            name = n["metadata"]["name"]
            if zone and n["metadata"]["labels"].get("topology.kubernetes.io/zone") != zone:
                continue
            if feasible(pods[i], n, used[name]):
                add = requests(pods[i])
                for k, v in add.items():
                    used[name][k] = used[name].get(k, 0) + v
                r = rec(i + 1)
                if r is not None:
                    return {i: name, **r}
                for k, v in add.items():
                    used[name][k] -= v
        return None

    return rec(0)
