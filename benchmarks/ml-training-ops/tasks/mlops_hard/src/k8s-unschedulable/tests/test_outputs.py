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
        assert req.get("memory", 0) >= 1600 * GI, "each pod needs at least 1600Gi"
        assert req.get("cpu", 0) >= 160, "each pod needs at least 160 CPUs"
        vols = {v["name"]: v for v in spec.get("volumes", [])}
        assert vols["dshm"]["emptyDir"].get("medium") == "Memory"
        assert vols["fsx"]["persistentVolumeClaim"]["claimName"] == "fsx-training"


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
