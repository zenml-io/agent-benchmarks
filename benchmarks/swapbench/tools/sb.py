#!/usr/bin/env python3
"""sb: the SwapBench verification toolkit given to arm 2.

  sb replay  --name NAME --model M [--llm-args JSON] [--policy-suffix FILE] [--split train|gen] [--trials K]
  sb compare --candidate NAME [--baseline traces|NAME] [--margin 5]
  sb pool                            extra unlabeled scenarios from the production mix (split "pool")
  sb runs                            list replays with cost so far

Replays run the production agent (tau2 llm_agent) with the production user simulator and mocked
tools. `compare` pairs scenarios with the baseline (default: the incumbent's production traces),
reports the success-rate change with a 95% cluster-bootstrap interval, the change in wrong database
writes, cost per conversation, and a gate decision:

  SAFE                   lower 95% bound of the change > -margin, and wrong writes not up
  UNSAFE                 upper 95% bound < -margin, or wrong writes clearly up
  INSUFFICIENT_EVIDENCE  otherwise (the interval straddles the margin): replay more scenarios

The "pool" split holds 200 more recent conversations' scenarios with no incumbent traces: to use
them, replay the incumbent on them as well, then `sb compare --candidate X --baseline INCUMBENT_RUN`.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys

TAU2 = os.environ.get("SB_TAU2", "/opt/tau2")
HOME = os.environ.get("SB_HOME", "/tmp/sb")
TRACES = os.environ.get("SB_TRACES", "/app/traces/visible/index.jsonl")
USER_LLM = os.environ.get("SB_USER_LLM", "anthropic/claude-haiku-5-5")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from swapbench import stats, tau2_adapter  # noqa: E402


def data_dir(suffix_file):
    """A private TAU2 data dir: production data (+ generated scenarios) with an optional policy suffix."""
    d = os.path.join(HOME, "data", os.path.basename(suffix_file or "plain"))
    if not os.path.exists(d):
        shutil.copytree(os.path.join(TAU2, "data"), d)
        if suffix_file:
            with open(os.path.join(d, "tau2", "domains", "retail", "policy.md"), "a") as f:
                f.write("\n\n" + open(suffix_file).read().strip() + "\n")
    return d


def replay(a):
    out = os.path.join(HOME, "runs", a.name)
    if os.path.exists(os.path.join(out, "results.json")):
        sys.exit(f"run {a.name} exists; pick another name")
    env = {**os.environ, "TAU2_DATA_DIR": data_dir(a.policy_suffix)}
    cmd = ["tau2", "run", "-d", "retail", "--agent-llm", a.model, "--agent-llm-args", a.llm_args, "--user-llm", USER_LLM,
           "--user-llm-args", "{}", "--task-split-name", a.split, "--num-trials", str(a.trials),
           "--max-concurrency", str(a.concurrency), "--save-to", out, "--log-level", "ERROR"]
    if a.num_tasks:
        cmd += ["--num-tasks", str(a.num_tasks)]
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out + ".log", "w") as log:
        rc = subprocess.run(cmd, cwd=TAU2, env=env, stdout=log, stderr=subprocess.STDOUT).returncode
    json.dump(vars(a) | {"rc": rc}, open(out + ".meta.json", "w"))
    summary(a.name)


def load(name):
    if name == "traces":
        return [json.loads(l) for l in open(TRACES)]
    return tau2_adapter.load(os.path.join(HOME, "runs", name, "results.json"))


def summary(name):
    eps = load(name)
    print(json.dumps({"run": name, "episodes": len(eps), "success_rate": round(stats.mean(eps, "reward"), 4),
                      "cost_per_conversation": round(stats.mean(eps, "cost_usd"), 5),
                      "wrong_writes_per_conversation": round(stats.mean(eps, "harmful_writes"), 4),
                      "api_errors": sum(bool(e.get("infra_error")) for e in eps)}))


def compare(a):
    cand, base = load(a.candidate), load(a.baseline)
    q = stats.paired_delta(cand, base, "reward")
    if not q["n"]:
        sys.exit("no shared scenarios between candidate and baseline")
    h = stats.paired_delta(cand, base, "harmful_writes")
    m = a.margin / 100
    harm_up = h["lo"] is not None and h["lo"] > 0.01
    if q["lo"] > -m and not (h["delta"] > 0.01 and h["lo"] > 0):
        gate = "SAFE"
    elif q["hi"] < -m or harm_up:
        gate = "UNSAFE"
    else:
        gate = "INSUFFICIENT_EVIDENCE"
    half = (q["hi"] - q["lo"]) / 2
    need = int(q["n"] * (half / max(abs(q["delta"] + m) or 1e-9, 0.01)) ** 2) if gate == "INSUFFICIENT_EVIDENCE" else None
    bc, cc = stats.mean(base, "cost_usd"), stats.mean(cand, "cost_usd")
    print(json.dumps({
        "candidate": a.candidate, "baseline": a.baseline, "shared_scenarios": q["n"],
        "success_change_pts": round(q["delta"] * 100, 2), "ci95_pts": [round(q["lo"] * 100, 2), round(q["hi"] * 100, 2)],
        "scenarios_worse": q["flips_down"], "scenarios_better": q["flips_up"],
        "wrong_writes_change_per_conv": round(h["delta"], 4), "wrong_writes_ci95": [round(h["lo"], 4), round(h["hi"], 4)],
        "cost_per_conv": {"baseline": round(bc, 5), "candidate": round(cc, 5), "cut": round(1 - cc / bc, 4) if bc else None},
        "margin_pts": a.margin, "gate": gate,
        "approx_scenarios_needed_for_a_decision": need,
    }, indent=1))


def pool(_):
    split = json.load(open(os.path.join(TAU2, "data", "tau2", "domains", "retail", "split_tasks.json")))
    print(f"{len(split.get('pool', []))} pool scenarios; use --split pool (and --num-tasks N for a subset)")


def runs(_):
    d = os.path.join(HOME, "runs")
    for n in sorted(os.listdir(d)) if os.path.exists(d) else []:
        if os.path.isdir(os.path.join(d, n)) and os.path.exists(os.path.join(d, n, "results.json")):
            summary(n)


def main():
    ap = argparse.ArgumentParser(prog="sb", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("replay")
    r.add_argument("--name", required=True)
    r.add_argument("--model", required=True)
    r.add_argument("--llm-args", default="{}")
    r.add_argument("--policy-suffix")
    r.add_argument("--split", default="train")
    r.add_argument("--trials", type=int, default=1)
    r.add_argument("--num-tasks", type=int)
    r.add_argument("--concurrency", type=int, default=10)
    c = sub.add_parser("compare")
    c.add_argument("--candidate", required=True)
    c.add_argument("--baseline", default="traces")
    c.add_argument("--margin", type=float, default=5.0)
    sub.add_parser("pool")
    sub.add_parser("runs")
    a = ap.parse_args()
    {"replay": replay, "compare": compare, "pool": pool, "runs": runs}[a.cmd](a)


if __name__ == "__main__":
    main()
