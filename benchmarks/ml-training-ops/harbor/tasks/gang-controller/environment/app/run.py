"""Run the controller in the simulator and check the scheduling invariants.

    python run.py --seeds 1 2 3            # prints a line per seed

Checked each tick (see README.md for the rules): no partial gang may hold GPUs for more than
PARTIAL_LIMIT consecutive ticks; the controller must not raise; every feasible job must finish by
DEADLINE ticks.
"""
import argparse
import importlib
import sys

from kube.sim import Api, ApiError, Cluster

PARTIAL_LIMIT = 5
DEADLINE = 1000


def check(seed, controller_module="controller", **kw):
    c = Cluster(seed, **kw)
    try:
        ctrl = importlib.import_module(controller_module).Controller(Api(c))
    except ApiError as e:
        return f"controller raised {type(e).__name__} in __init__: {e}", 0
    total = sum(n["gpus"] for n in c.nodes.values())
    per_node = max(n["gpus"] for n in c.nodes.values())
    partial_for = {}
    for _ in range(DEADLINE):
        try:
            ctrl.step()
        except ApiError as e:
            return f"controller raised {type(e).__name__}: {e} at tick {c.tick}", c.tick
        c.advance()
        for jn, j in c.jobs.items():
            if j["state"] == "Succeeded":
                continue
            bound = [p for p in c.pods.values() if p["job"] == jn and p["node"]]
            if 0 < len(bound) < j["pods"]:
                partial_for[jn] = partial_for.get(jn, 0) + 1
                if partial_for[jn] > PARTIAL_LIMIT:
                    return f"{jn} held a partial gang ({len(bound)}/{j['pods']} pods) for >{PARTIAL_LIMIT} ticks at tick {c.tick}", c.tick
            else:
                partial_for[jn] = 0
        feasible = [j for j in c.jobs.values() if j["pods"] * j["gpus_per_pod"] <= total and j["gpus_per_pod"] <= per_node]
        if not c.arrivals and feasible and all(j["state"] == "Succeeded" for j in feasible) and \
                len(feasible) + sum(1 for j in c.jobs.values() if j not in feasible) == len(c.jobs):
            return None, c.tick
    left = [jn for jn, j in c.jobs.items() if j["state"] != "Succeeded" and j["pods"] * j["gpus_per_pod"] <= total]
    return f"{len(left)} feasible jobs not finished by tick {DEADLINE}: {left[:5]}", c.tick


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, nargs="+", default=[1, 2, 3])
    ap.add_argument("--controller", default="controller")
    a = ap.parse_args()
    bad = 0
    for s in a.seeds:
        err, t = check(s, a.controller)
        print(f"seed {s}: {'OK, all feasible jobs done at tick ' + str(t) if err is None else 'FAIL: ' + err}")
        bad += err is not None
    sys.exit(1 if bad else 0)
