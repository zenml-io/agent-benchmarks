import copy
import os
import sys

import pytest
import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import sched  # noqa: E402

APP = os.environ.get("APP_DIR", "/app")
GI = 2 ** 30
IMAGE = "123456789012.dkr.ecr.us-east-1.amazonaws.com/llm/train:2026.10.2"
CMD = ["python", "-m", "llm.train", "--config", "configs/cpt-1010.yaml"]
ZONE = "topology.kubernetes.io/zone"


@pytest.fixture(scope="module")
def job():
    docs = [d for d in yaml.safe_load_all(open(os.path.join(APP, "job", "pytorchjob.yaml"))) if d]
    assert len(docs) == 1 and docs[0]["kind"] == "PyTorchJob"
    return docs[0]


@pytest.fixture(scope="module")
def cluster():
    # pristine copies: the agent's edits to /app/cluster do not change the cluster
    return sched.load_cluster(os.path.join(HERE, "nodes.yaml"), os.path.join(HERE, "pods.yaml"))


def pods_of(job):
    out = []
    for rtype, n in (("Master", 1), ("Worker", 3)):
        rs = job["spec"]["pytorchReplicaSpecs"][rtype]
        assert int(rs["replicas"]) == n, f"{rtype} replicas changed"
        t = rs["template"]
        for _ in range(n):
            out.append((copy.deepcopy(t["spec"]), (t.get("metadata") or {}).get("labels") or {}))
    return out


def test_job_unchanged_where_it_matters(job):
    assert job["metadata"]["name"] == "cpt-1010" and job["metadata"].get("namespace") == "training"
    assert str(job["spec"]["nprocPerNode"]) == "8"
    for spec, _ in pods_of(job):
        (c,) = [c for c in spec["containers"] if c["name"] == "pytorch"]
        assert c["image"] == IMAGE and c["command"] == CMD
        req = sched.requests({"containers": [c]})
        lim = {k: sched.qty(v) for k, v in (c["resources"].get("limits") or {}).items()}
        assert req.get("nvidia.com/gpu") == 8 and lim.get("nvidia.com/gpu") == 8
        assert req.get("vpc.amazonaws.com/efa") == 32
        assert req.get("memory", 0) >= 1000 * GI, "each pod needs at least 1000Gi"
        assert req.get("cpu", 0) >= 80, "each pod needs at least 80 CPUs"
        vols = {v["name"]: v for v in spec.get("volumes", [])}
        assert vols["dshm"]["emptyDir"].get("medium") == "Memory"
        assert vols["fsx"]["persistentVolumeClaim"]["claimName"] in ("fsx-training", "fsx-training-b"), \
            "the job's data and checkpoints live on fsx-training (and its replica fsx-training-b)"


def test_policy(job):
    for spec, _ in pods_of(job):
        for t in spec.get("tolerations") or []:
            assert t.get("key") not in ("dedicated",), "must not tolerate dedicated taints"
            assert not (t.get("key") in (None, "") and t.get("operator") == "Exists"), "blanket toleration"
            assert t.get("key") != "node.kubernetes.io/unschedulable", "must not schedule onto cordoned nodes"


def test_all_pods_schedule_in_one_zone(job, cluster):
    nodes, used = cluster
    pods = [s for s, _ in pods_of(job)]
    zones_of = lambda names: {n["metadata"]["labels"][ZONE] for n in nodes if n["metadata"]["name"] in names}  # noqa: E731
    placement = sched.assign(pods, nodes, used)
    assert placement is not None, "the scheduler cannot place all 4 pods"
    # a single zone must be guaranteed by the spec, not left to luck: either every node any pod
    # could use is in one zone, or a required pod affinity on the zone keeps the gang together
    feas = {n["metadata"]["name"] for s in pods for n in nodes if sched.feasible(s, n, used[n["metadata"]["name"]])}
    if len(zones_of(feas)) > 1:
        for spec, labels in pods_of(job):
            terms = (((spec.get("affinity") or {}).get("podAffinity") or {})
                     .get("requiredDuringSchedulingIgnoredDuringExecution") or [])
            ok = any(t.get("topologyKey") == ZONE and all(labels.get(k) == v for k, v in
                     ((t.get("labelSelector") or {}).get("matchLabels") or {}).items()) and
                     (t.get("labelSelector") or {}).get("matchLabels") for t in terms)
            assert ok, f"pods could be spread over zones {sorted(zones_of(feas))}"
        assert any(sched.assign(pods, nodes, used, zone=z) for z in zones_of(feas)), "no single zone fits the gang"


def pv_zone(claim):
    items = yaml.safe_load(open(os.path.join(HERE, "storage.yaml")))["items"]
    pvc = next(i for i in items if i["kind"] == "PersistentVolumeClaim" and i["metadata"]["name"] == claim)
    pv = next(i for i in items if i["kind"] == "PersistentVolume" and i["metadata"]["name"] == pvc["spec"]["volumeName"])
    return pv["spec"]["nodeAffinity"]["required"]["nodeSelectorTerms"][0]["matchExpressions"][0]["values"][0]


def test_admission_quota_and_limits(job):
    """Pods must pass LimitRange and ResourceQuota admission (otherwise they are never created)."""
    items = yaml.safe_load(open(os.path.join(HERE, "namespace-limits.yaml")))["items"]
    quota = next(i for i in items if i["kind"] == "ResourceQuota")
    lr = next(i for i in items if i["kind"] == "LimitRange")["spec"]["limits"][0]
    tot = {}
    for spec, _ in pods_of(job):
        for c in spec["containers"]:
            res = c.get("resources") or {}
            req = sched.requests({"containers": [c]})
            lim = {k: sched.qty(v) for k, v in (res.get("limits") or {}).items()}
            for k, mx in lr["max"].items():
                if k in lim:
                    assert lim[k] <= sched.qty(mx), f"LimitRange: {k} limit {lim[k]:.3g} above max {mx}"
            ratio = float(lr["maxLimitRequestRatio"]["memory"])
            if "memory" in lim:
                assert lim["memory"] <= ratio * req["memory"] + 1, "LimitRange: memory limit/request ratio above 1.5"
            for k, v in req.items():
                tot["requests." + k] = tot.get("requests." + k, 0) + v
            for k, v in lim.items():
                tot["limits." + k] = tot.get("limits." + k, 0) + v
    for k, hard in quota["status"]["hard"].items():
        used = sched.qty(quota["status"]["used"].get(k, "0"))
        assert used + tot.get(k, 0) <= sched.qty(hard) + 1, f"ResourceQuota {k}: {used + tot.get(k, 0):.4g} > {hard}"


def test_storage_zone_matches_placement(job, cluster):
    nodes, used = cluster
    pods = [s for s, _ in pods_of(job)]
    claim = {v["name"]: v for v in pods[0]["volumes"]}["fsx"]["persistentVolumeClaim"]["claimName"]
    z = pv_zone(claim)
    assert sched.assign(pods, nodes, used, zone=z), f"the volume {claim} is in {z}, but the gang cannot be placed there"
    feas = {n["metadata"]["name"] for s in pods for n in nodes if sched.feasible(s, n, used[n["metadata"]["name"]])}
    bad = sorted(n["metadata"]["name"] for n in nodes if n["metadata"]["name"] in feas
                 and n["metadata"]["labels"][ZONE] != z)
    assert not bad, f"pods could land on {bad}, outside the volume's zone {z} (volume attach would fail)"
