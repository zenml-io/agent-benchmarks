"""
Frontier-model runs on the hard ML-training-ops tasks through vendor APIs (no GPU server):
Claude Code with Anthropic models, Codex with OpenAI models, and terminus-2 with either.

    ANTHROPIC_API_KEY=... OPENAI_API_KEY=... python api_runs.py run --harness claude-code \
        --model anthropic/claude-sonnet-5-5 --attempts 1
    python api_runs.py report

Keys come only from the environment; nothing here writes them anywhere. Every run is appended to
api_attempts.jsonl with token counts and its API cost: the harness's own figure when it reports one,
otherwise tokens x the price table below (whichever is higher, to stay conservative). A run is
refused if the provider's recorded spend plus a pessimistic estimate for the run would exceed the
provider's budget (--budget, USD).
"""
import argparse
import glob
import json
import os
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]  # the benchmark dir: data/, tasks/, jobs/, new logs
JOBS = HERE / "jobs"
LOG = HERE / os.environ.get("API_LOG", "api_attempts.jsonl")  # separate logs let two sessions run in parallel
# USD per 1M tokens: input, cached input, output (Anthropic: claude-api skill table, Oct 2026;
# OpenAI: third-party aggregators, Oct 2026; verify before relying on them).
PRICES = {
    "claude-haiku-5-5": (0.10, 0.01, 0.50), "claude-sonnet-5-5": (2.0, 0.20, 10.0),
    "claude-opus-5-5": (4.0, 0.20, 20.0), "claude-fable-5-1": (10.0, 0.25, 50.0),
    "gpt-6-luna": (0.10, 0.01, 0.50), "gpt-6.1-sol": (2.0, 0.10, 10.0), "gpt-6-sol": (2.0, 0.20, 10.0),
    "gpt-6-astra": (10.0, 1.0, 50.0),
}


def provider(model):
    return "anthropic" if model.split("/")[-1].startswith("claude") else "openai"


def spent(prov):
    if not LOG.exists():
        return 0.0
    return sum(json.loads(l)["api_cost"] for l in open(LOG) if json.loads(l)["provider"] == prov)


def parse_job(job_dir, model):
    p_in, p_cache, p_out = PRICES[model.split("/")[-1]]
    trials, cost = [], 0.0
    for rf in glob.glob(str(job_dir / "*" / "result.json")):
        d = Path(rf).parent
        r = json.load(open(rf))
        a = r.get("agent_result") or {}
        rw = d / "verifier" / "reward.txt"
        reward = float(rw.read_text().strip()) if rw.exists() else 0.0
        n_in, n_cache, n_out = a.get("n_input_tokens") or 0, a.get("n_cache_tokens") or 0, a.get("n_output_tokens") or 0
        est = ((n_in - n_cache) * p_in + n_cache * p_cache + n_out * p_out) / 1e6
        c = max(a.get("cost_usd") or 0.0, est)
        cost += c
        trials.append({"task": d.name.split("__")[0], "reward": reward, "cost": round(c, 4), "n_input": n_in,
                       "n_cache": n_cache, "n_output": n_out,
                       "exc": (r.get("exception_info") or {}).get("exception_type")})
    return trials, cost


def run(a):
    TASKS = json.load(open(HERE / a.tasks_file))
    JOBS.mkdir(exist_ok=True)
    prov = provider(a.model)
    key = "ANTHROPIC_API_KEY" if prov == "anthropic" else "OPENAI_API_KEY"
    # Cloud sessions reserve ANTHROPIC_API_KEY for themselves, so the eval key can come in under
    # EVAL_ANTHROPIC_API_KEY; it is passed to the harness as ANTHROPIC_API_KEY.
    if prov == "anthropic" and os.environ.get("EVAL_ANTHROPIC_API_KEY"):
        os.environ["ANTHROPIC_API_KEY"] = os.environ["EVAL_ANTHROPIC_API_KEY"]
        os.environ.pop("ANTHROPIC_BASE_URL", None)  # talk to the real API, not this session's proxy
    if not os.environ.get(key):
        sys.exit(f"{key} is not set")
    already = spent(prov)
    if already + a.estimate > a.budget:
        sys.exit(f"refusing: {prov} spent ${already:.2f}, estimate ${a.estimate:.2f}, budget ${a.budget:.2f}")
    tag = os.path.splitext(os.path.basename(a.tasks_file))[0].replace("tasks_", "")
    name = f"api-{tag}-k{a.attempts}__{a.harness}__{a.model.split('/')[-1]}__{time.strftime('%Y%m%d-%H%M%S')}"
    cmd = ["harbor", "run", "-y", "-p", str(HERE / TASKS["path"]), "-a", a.harness, "-m", a.model, "-e", "modal",
           "-n", str(a.concurrency), "-o", str(JOBS), "--job-name", name, "--ek", "sandbox_timeout_secs=7200"]
    if a.attempts > 1:
        cmd += ["-k", str(a.attempts)]
    for t in (a.tasks or TASKS["tasks"]):
        cmd += ["-i", t]
    print(f"[{a.harness} | {a.model}] spent so far ${already:.2f} of ${a.budget:.2f}; job {name}", flush=True)
    t0 = time.time()
    with open(JOBS / f"{name}.log", "w") as f:
        rc = subprocess.run(cmd, stdout=f, stderr=subprocess.STDOUT, env={**os.environ, "MODAL_ENVIRONMENT": os.environ.get("MODAL_ENVIRONMENT", "main")}).returncode
    trials, cost = parse_job(JOBS / name, a.model)
    rec = {"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "job_name": name, "harness": a.harness,
           "model": a.model, "provider": prov, "attempts_per_task": a.attempts, "task_set": tag, "concurrency": a.concurrency,
           "attempted": len(trials), "solved": int(sum(t["reward"] >= 1 for t in trials)),
           "api_cost": round(cost, 4), "wall_s": round(time.time() - t0), "harbor_rc": rc, "trials": trials}
    with open(LOG, "a") as f:
        f.write(json.dumps(rec) + "\n")
    print(json.dumps({k: v for k, v in rec.items() if k != "trials"}, indent=1), flush=True)
    print(f"{prov} spent now ${spent(prov):.2f} of ${a.budget:.2f}", flush=True)


def report(_):
    for l in open(LOG):
        r = json.loads(l)
        per = r["api_cost"] / max(r["solved"], 1)
        print(f"{r['harness']:12s} {r['model']:30s} k={r['attempts_per_task']} solved {r['solved']}/{r['attempted']} "
              f"API ${r['api_cost']:.2f} (${per:.2f}/solve) {r['wall_s']}s")
    for p in ("anthropic", "openai"):
        print(p, f"total ${spent(p):.2f}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--harness", required=True)
    r.add_argument("--model", required=True)
    r.add_argument("--attempts", type=int, default=1)
    r.add_argument("--concurrency", type=int, default=8)
    r.add_argument("--tasks", nargs="*")
    r.add_argument("--tasks-file", default="data/tasks_mlops_hard.json")
    r.add_argument("--budget", type=float, default=160.0)
    r.add_argument("--estimate", type=float, default=0.0, help="pessimistic cost estimate for this run (USD)")
    sub.add_parser("report")
    a = ap.parse_args()
    {"run": run, "report": report}[a.cmd](a)
