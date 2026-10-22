"""Full grid scheduler: one queue per provider, run in parallel; jobs inside a queue run one at a time.

  python harness/grid.py [--cap 430] [--dry]

Before each job it sums the actual spend so far (results/**.jsonl costs, plus the support runs' converted rows and
their simulator cost) and skips the job if the total is over the cap. Finished tasks are skipped by run.py, so the
grid can be restarted safely.
"""
import argparse
import glob
import json
import os
import subprocess
import sys
import threading
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UCS = ["kyc_checks", "pr_review", "sql_analyst", "it_access", "invoice_extraction", "claims_triage",
       "contract_review", "lead_qualification", "meeting_to_crm"]
JEV_UCS = ["kyc_checks", "pr_review", "it_access", "invoice_extraction", "claims_triage", "lead_qualification"]
JEV_MODELS = ["haiku-5.5", "gpt-6-luna", "deepseek-v4.1-flash@provider-a", "glm-5.3-flash@provider-b",
              "gpt-oss-120b@provider-a", "qwen3.8-27b@provider-a"]
# The original run used 48.66 here. A fresh rerun starts at 0; set HT_SPENT_BEFORE to count spend made elsewhere.
SPENT_BEFORE = float(os.environ.get("HT_SPENT_BEFORE", "0"))  # original value 48.66: spend outside results/ (smoke, sanity, gpt-oss debug, $39.62 of claims runs on the nondeterministic generator in results_claims_v1_nondeterministic/, and the superseded pilot gpt-oss rows: $0.33 kept in sanity/pilot_old_code, $0.46 overwritten; costs.md); the pilot is in results/

QUEUES = {
    "anthropic": [("haiku-5.5", 8), ("sonnet-5.5", 8), ("opus-5.5", 8)],
    "openai": [("gpt-6-luna", 8), ("gpt-6.1-sol", 8)],
    "provider-a": [("deepseek-v4.1-flash@provider-a", 8), ("gpt-oss-120b@provider-a", 8), ("glm-5.3-flash@provider-a", 8),
               ("qwen3.8-27b@provider-a", 8), ("deepseek-v4-pro@provider-a", 8), ("glm-5.3@provider-a", 8)],
    "provider-b": [("deepseek-v4.1-flash@provider-b", 4), ("gpt-oss-120b@provider-b", 4), ("glm-5.3-flash@provider-b", 4),
                ("kimi-k3@provider-b", 4), ("deepseek-v4-pro@provider-b", 4), ("glm-5.3@provider-b", 4)],
}
SUPPORT = ["haiku-5.5", "gpt-6-luna", "gpt-6.1-sol", "sonnet-5.5", "opus-5.5", "gpt-oss-120b@provider-a",
           "glm-5.3-flash@provider-b", "deepseek-v4.1-flash@provider-b", "kimi-k3@provider-b", "deepseek-v4-pro@provider-b",
           "glm-5.3@provider-b", "glm-5.3-flash@provider-a", "deepseek-v4-pro@provider-a", "glm-5.3@provider-a", "gpt-oss-120b@provider-b"]


def spent():
    t = SPENT_BEFORE
    for p in glob.glob(os.path.join(ROOT, "results", "*", "*.jsonl")):
        for l in open(p):
            r = json.loads(l)
            if not r.get("reused"):
                t += r.get("cost", 0) + r.get("sim_cost", 0)
    return t


def log(msg):
    line = f"{time.strftime('%H:%M:%S')} {msg}"
    print(line, flush=True)
    os.makedirs(os.path.join(ROOT, "logs"), exist_ok=True)
    with open(os.path.join(ROOT, "logs", "grid.log"), "a") as f:
        f.write(line + "\n")


def queue(name, jobs, cap, dry):
    for uc, model, arm, workers in jobs:
        s = spent()
        if s > cap:
            log(f"[{name}] SKIP {uc} {model} {arm}: spend ${s:.2f} over cap ${cap}")
            continue
        log(f"[{name}] start {uc} {model} {arm} (spend ${s:.2f})")
        if dry:
            continue
        if uc == "support":
            subprocess.run([os.path.join(os.environ.get("TAU2_PY", sys.executable)), "harness/support_tau2.py", "run",
                            model], cwd=ROOT, stdout=open(os.path.join(ROOT, "logs", f"support.{model}.log"), "a"),
                           stderr=subprocess.STDOUT)
            subprocess.run([os.environ.get("TAU2_PY", sys.executable), "harness/support_tau2.py", "convert"], cwd=ROOT,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            subprocess.run([sys.executable, "harness/run.py", uc, model, "--arm", arm, "--n", "100", "--workers",
                            str(workers)], cwd=ROOT,
                           stdout=open(os.path.join(ROOT, "logs", f"{uc}.{model}.{arm}.log"), "a"),
                           stderr=subprocess.STDOUT)
        log(f"[{name}] done {uc} {model} {arm}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cap", type=float, default=430)
    ap.add_argument("--dry", action="store_true")
    a = ap.parse_args()
    plans = {}
    for q, models in QUEUES.items():
        jobs = [(uc, m, "none", w) for m, w in models for uc in UCS]
        jobs += [(uc, m, "jev", w) for m, w in models if m in JEV_MODELS for uc in JEV_UCS]
        plans[q] = jobs
    # The support use case needs the private SwapBench hidden split and harness/support_tau2.py, which are not in this
    # public repo; it is scheduled only when that runner is present.
    if os.path.exists(os.path.join(ROOT, "harness", "support_tau2.py")):
        plans["support"] = [("support", m, "none", 0) for m in SUPPORT]
    log(f"grid start: {sum(len(j) for j in plans.values())} jobs, cap ${a.cap}, spend so far ${spent():.2f}")
    ts = [threading.Thread(target=queue, args=(q, j, a.cap, a.dry)) for q, j in plans.items()]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    log(f"grid end: spend ${spent():.2f}")


if __name__ == "__main__":
    main()
