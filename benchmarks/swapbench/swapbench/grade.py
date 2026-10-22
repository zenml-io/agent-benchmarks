"""Grade arm submissions against the hidden set.

  python -m swapbench.grade <harbor_job_dir> --task retail-refunds --gt <ground_truth_dir> \
      --tau2 <tau2 checkout with the hidden split> --tau2-env <venv> [--out experiments/graded.jsonl]

For each trial, it:
1. reads the submission the verifier printed (config.yaml + verdict.json);
2. gets the submitted config's episodes on the hidden set H. A plain model with no prompt suffix
   or args reuses the ground-truth run for that model string; anything else is replayed on H with
   tau2, with the policy suffix applied to a private copy of the data dir;
3. compares them with the incumbent on H (paired cluster bootstrap) and assigns a truth label;
4. scores the declaration: false-safe, correct-safe, missed savings, correct abstention.
"""
import argparse
import glob
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile

import yaml

from . import stats, tau2_adapter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def read_submission(trial_dir):
    for f in glob.glob(os.path.join(trial_dir, "verifier", "*")):
        try:
            text = open(f, errors="replace").read()
        except IsADirectoryError:
            continue
        m = re.search(r"===SWAPBENCH-CONFIG===\n(.*?)===SWAPBENCH-VERDICT===\n(.*?)===SWAPBENCH-END===", text, re.S)
        if m:
            try:
                cfg = yaml.safe_load(m.group(1)) or {}
            except yaml.YAMLError:
                cfg = {}
            try:
                verdict = json.loads(m.group(2))
            except json.JSONDecodeError:
                verdict = {}
            return cfg, verdict
    return None, None


def config_key(cfg):
    return hashlib.sha256(json.dumps([cfg.get("model"), cfg.get("llm_args") or {}, cfg.get("policy_suffix") or ""],
                                     sort_keys=True).encode()).hexdigest()[:12]


def hidden_results(cfg, spec, gt_dir, tau2_dir, tau2_env, cache_dir, data_dir=None, max_scenarios=None):
    model = str(cfg.get("model", "")).strip()
    plain = not (cfg.get("llm_args") or {}) and not (cfg.get("policy_suffix") or "").strip()
    gt = os.path.join(gt_dir, model.replace("/", "_"), spec["sets"]["hidden"]["split"], "results.json")
    if plain and os.path.exists(gt):
        return gt
    out = os.path.join(cache_dir, config_key(cfg))
    res = os.path.join(out, "results.json")
    if os.path.exists(res):
        return res
    data_root = tempfile.mkdtemp(prefix="swapbench-data-")
    shutil.copytree(data_dir or os.path.join(tau2_dir, "data"), os.path.join(data_root, "data"),
                    ignore=shutil.ignore_patterns("results", "voice"))
    if (cfg.get("policy_suffix") or "").strip():
        p = os.path.join(data_root, "data", "tau2", "domains", spec["source"]["domain"], "policy.md")
        open(p, "a").write("\n\n" + cfg["policy_suffix"].strip() + "\n")
    hid = spec["sets"]["hidden"]
    cmd = [os.path.join(tau2_env, "bin", "tau2"), "run", "-d", spec["source"]["domain"], "--agent-llm", model,
           "--agent-llm-args", json.dumps(cfg.get("llm_args") or {}),
           "--user-llm", spec["user_simulator"]["model"], "--user-llm-args", json.dumps(spec["user_simulator"]["args"]),
           "--task-split-name", hid["split"], "--num-trials", str(hid["trials"]), "--max-concurrency", "8",
           "--save-to", out, "--log-level", "ERROR"]
    if max_scenarios:  # budget: grade on the first N hidden scenarios (paired with the incumbent on the same ones)
        cmd += ["--num-tasks", str(max_scenarios)]
    env = {**os.environ, "TAU2_DATA_DIR": os.path.join(data_root, "data")}
    env["ANTHROPIC_API_KEY"] = os.environ.get("EVAL_ANTHROPIC_API_KEY", os.environ.get("ANTHROPIC_API_KEY", ""))
    os.makedirs(out, exist_ok=True)
    with open(out + ".log", "w") as log:
        subprocess.run(cmd, cwd=tau2_dir, env=env, stdout=log, stderr=subprocess.STDOUT, timeout=7200)
    shutil.rmtree(data_root, ignore_errors=True)
    return res if os.path.exists(res) else None


def score(decision, label, cost_cut, target):
    if decision == "SAFE":
        return {"REGRESSED": "false_safe", "NON-INFERIOR": "correct_safe", "AMBIGUOUS": "safe_ambiguous"}[label]
    if label == "NON-INFERIOR" and cost_cut >= target:
        return "missed_savings"
    if label == "REGRESSED":
        return "correct_reject"
    return "abstain_other"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("job_dir")
    ap.add_argument("--task", default="retail-refunds")
    ap.add_argument("--gt", required=True)
    ap.add_argument("--tau2", required=True)
    ap.add_argument("--tau2-env", required=True)
    ap.add_argument("--out", default=os.path.join(ROOT, "experiments", "graded.jsonl"))
    ap.add_argument("--data-dir", help="TAU2_DATA_DIR of generated scenarios (tasks with source.generated)")
    ap.add_argument("--max-scenarios", type=int, help="replay non-ground-truth configs on only the first N hidden scenarios")
    a = ap.parse_args()
    spec = yaml.safe_load(open(os.path.join(ROOT, "tasks", a.task, "task.yaml")))
    margin = spec["acceptance"]["margin_pts"] / 100
    inc_res = os.path.join(a.gt, spec["incumbent"]["model"].replace("/", "_"), spec["sets"]["hidden"]["split"], "results.json")
    inc = tau2_adapter.load(inc_res, spec["source"]["domain"])
    cache = os.path.join(os.path.dirname(a.gt.rstrip("/")), f"graded_configs_{a.task}")
    for trial in sorted(glob.glob(os.path.join(a.job_dir, "*__*"))):
        if not os.path.isdir(trial):
            continue
        cfg, verdict = read_submission(trial)
        rec = {"job": os.path.basename(a.job_dir.rstrip("/")), "trial": os.path.basename(trial), "task": a.task,
               "config": cfg, "decision": (verdict or {}).get("decision"), "verdict": verdict}
        if not cfg or not cfg.get("model"):
            rec.update(outcome="no_submission")
        else:
            res = hidden_results(cfg, spec, a.gt, a.tau2, a.tau2_env, cache, a.data_dir, a.max_scenarios)
            if not res:
                rec.update(outcome="grading_failed")
            else:
                eps = tau2_adapter.load(res, spec["source"]["domain"])
                q = stats.paired_delta(eps, inc, "reward")
                h = stats.paired_delta(eps, inc, "harmful_writes")
                shared = {e["scenario"] for e in eps}
                cut = 1 - stats.mean(eps, "cost_usd") / stats.mean([e for e in inc if e["scenario"] in shared], "cost_usd")
                label = stats.truth_label(q, h, margin)
                rec.update(hidden=dict(delta=q, harm=h, cost_cut=cut, scenarios=q["n"], reward=stats.mean(eps, "reward"),
                                       incumbent_reward=stats.mean([e for e in inc if e["scenario"] in shared], "reward"), api_errors=sum(e["infra_error"] for e in eps)),
                           truth=label, outcome=score(rec["decision"], label, cut, spec["acceptance"]["target_cost_cut"]))
        print(json.dumps({k: rec.get(k) for k in ("trial", "decision", "truth", "outcome")}), flush=True)
        with open(a.out, "a") as f:
            f.write(json.dumps(rec) + "\n")


if __name__ == "__main__":
    main()
