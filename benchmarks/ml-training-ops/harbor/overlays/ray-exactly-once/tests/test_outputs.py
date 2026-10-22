"""Run the pipeline against a Ray cluster while killing Ray worker processes at random moments.
Every run must finish, write exact totals, and the live `totals` actor must never report more than
the true total for any user (no transient double counting)."""
import glob
import json
import os
import random
import shutil
import signal
import subprocess
import sys
import threading
import time

import pytest

APP = os.environ.get("APP_DIR", "/app")
RAY = os.path.join(os.path.dirname(sys.executable), "ray")
RATES = {"USD": (1, 1), "EUR": (108, 100), "GBP": (127, 100), "JPY": (67, 10000)}


def truth():
    seen, tot = set(), {}
    for p in sorted(glob.glob(os.path.join(APP, "data/shards/*.jsonl"))):
        for line in open(p):
            e = json.loads(line)
            if e["status"] != "settled" or e["id"] in seen:
                continue
            seen.add(e["id"])
            n, d = RATES[e["currency"]]
            u = e["user"].strip().lower()
            tot[u] = tot.get(u, 0) + e["amount"] * n // d
    return tot


TRUTH = truth()


@pytest.fixture(scope="module")
def cluster():
    subprocess.run([RAY, "stop", "--force"], capture_output=True)
    r = subprocess.run([RAY, "start", "--head", "--num-cpus=4", "--disable-usage-stats", "--include-dashboard=false"],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    import ray
    ray.init(address="auto", namespace="payments", logging_level="ERROR")
    yield ray
    ray.shutdown()
    subprocess.run([RAY, "stop", "--force"], capture_output=True)


def ray_workers():
    out = subprocess.run(["ps", "-eo", "pid,args"], capture_output=True, text=True).stdout.splitlines()[1:]
    procs = []
    for line in out:
        pid, _, args = line.strip().partition(" ")
        if args.startswith("ray::") and not args.startswith("ray::IDLE"):
            procs.append((int(pid), args))
    return procs


def run(ray, seed, kills):
    rng = random.Random(seed)
    shutil.rmtree(os.path.join(APP, "out"), ignore_errors=True)
    env = {**os.environ, "RAY_ADDRESS": "auto"}
    p = subprocess.Popen([sys.executable, "pipeline.py"], cwd=APP, env=env, stdout=subprocess.PIPE,
                         stderr=subprocess.STDOUT, text=True)
    stop = threading.Event()
    violations, seen_workers, killed = [], set(), []

    def monitor():
        while not stop.is_set():
            try:
                cur = ray.get(ray.get_actor("totals").get_all.remote(), timeout=2)
                bad = {u: v for u, v in cur.items() if v > TRUTH.get(u, 0)}
                if bad:
                    violations.append(sorted(bad.items())[:3])
            except Exception:  # noqa: BLE001 - actor restarting or not created yet
                pass
            for pid, args in ray_workers():
                seen_workers.add(args.split(".")[0])
            time.sleep(0.25)

    def chaos():
        times = sorted(rng.uniform(1.5, 14.0) for _ in range(kills))
        t0 = time.time()
        for t in times:
            while time.time() - t0 < t and not stop.is_set():
                time.sleep(0.05)
            procs = ray_workers()
            if not procs or stop.is_set():
                continue
            totals = [x for x in procs if x[1].startswith("ray::Totals")]
            pid, args = rng.choice(totals) if totals and rng.random() < 0.35 else rng.choice(procs)
            try:
                os.kill(pid, signal.SIGKILL)
                killed.append(args)
            except ProcessLookupError:
                pass

    th = [threading.Thread(target=monitor, daemon=True), threading.Thread(target=chaos, daemon=True)]
    for t in th:
        t.start()
    try:
        out, _ = p.communicate(timeout=240)
    except subprocess.TimeoutExpired:
        p.kill()
        stop.set()
        pytest.fail(f"seed {seed}: pipeline hung (killed {killed})")
    stop.set()
    for t in th:
        t.join(timeout=5)
    assert p.returncode == 0, f"seed {seed}: pipeline failed after killing {killed}:\n{out[-2500:]}"
    got = json.load(open(os.path.join(APP, "out", "totals.json")))
    wrong = {u: (got.get(u), v) for u, v in TRUTH.items() if got.get(u) != v}
    assert not wrong and set(got) == set(TRUTH), \
        f"seed {seed}: {len(wrong)} users wrong after killing {killed}, e.g. {list(wrong.items())[:3]}"
    assert not violations, f"seed {seed}: live totals exceeded the true totals: {violations[:2]}"
    assert len(seen_workers) >= 2, "the pipeline must run its work in Ray workers"
    check_live_totals_final(ray, seed, killed)
    return killed


def check_live_totals_final(ray, seed, killed):
    """Added for the Harbor-native version: the dashboard reads the `totals` actor, so once the job is done
    the actor must hold the exact totals too (a driver that computes the file itself while the actor
    stays empty passed the original checks)."""
    deadline, last = time.time() + 60, None
    while time.time() < deadline:
        try:
            last = ray.get(ray.get_actor("totals").get_all.remote(), timeout=10)
            if last == TRUTH:
                return
        except Exception as e:  # noqa: BLE001 - actor restarting after a kill
            last = repr(e)
        time.sleep(1)
    wrong = last if not isinstance(last, dict) else {u: (last.get(u), v) for u, v in TRUTH.items() if last.get(u) != v}
    pytest.fail(f"seed {seed}: after the job, the live totals actor does not hold the true totals "
                f"(killed {killed}): {str(wrong)[:300]}")


def test_clean_run(cluster):
    run(cluster, seed=0, kills=0)


@pytest.mark.parametrize("seed", [11, 12, 13, 14, 15, 16])
def test_chaos(cluster, seed):
    run(cluster, seed=seed, kills=random.Random(seed).randint(3, 8))
