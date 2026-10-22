"""Rebuild every environment's tasks offline and print the test-set facts the write-up relies on.

  uv run python scripts/check_tasks.py [--seeds 0,1,2,3] [--json out.json]

For each of the nine harness use cases: tasks generated, the 100 test tasks (first 100 in id-hash order, as in
harness/run.py), how many of them the grader audit keeps (audit_exclusions.json), and a SHA-256 fingerprint of the test
tasks (id, request, gold, triggers). The fingerprint is computed under each PYTHONHASHSEED in --seeds in a fresh
process: the published runs pinned PYTHONHASHSEED=0, and the tasks listed in harness/audit.py UNSTABLE are the ones
whose data still varies with the seed. No model calls, no network.
"""
import argparse
import hashlib
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UCS = ["invoice_extraction", "claims_triage", "kyc_checks", "contract_review", "sql_analyst", "lead_qualification",
       "it_access", "pr_review", "meeting_to_crm"]

CHILD = r"""
import hashlib, importlib, json, sys
sys.path.insert(0, sys.argv[1])
out = {}
for uc in sys.argv[2].split(","):
    tasks = importlib.import_module("envs." + uc).ENV.tasks()
    test = sorted(tasks, key=lambda t: hashlib.sha256(t["id"].encode()).hexdigest())[:100]
    per = {t["id"]: hashlib.sha256(json.dumps([t["request"], t["gold"], sorted(t.get("triggers", []))],
                                              sort_keys=True, default=str).encode()).hexdigest() for t in test}
    out[uc] = {"generated": len(tasks), "test_ids": [t["id"] for t in test], "per_task": per,
               "fingerprint": hashlib.sha256(json.dumps(per, sort_keys=True).encode()).hexdigest()[:16],
               "test_with_hidden_rule": sum(bool(t.get("triggers")) for t in test)}
print(json.dumps(out))
"""


def build(seed):
    env = dict(os.environ, PYTHONHASHSEED=str(seed))
    r = subprocess.run([sys.executable, "-c", CHILD, ROOT, ",".join(UCS)], env=env, capture_output=True, text=True,
                       check=True)
    return json.loads(r.stdout)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", default="0,1,2,3")
    ap.add_argument("--json")
    a = ap.parse_args()
    seeds = [int(s) for s in a.seeds.split(",")]
    runs = {s: build(s) for s in seeds}
    excl = json.load(open(os.path.join(ROOT, "audit_exclusions.json")))
    base = runs[seeds[0]]
    print(f"{'use case':20s} {'generated':>9s} {'test':>5s} {'kept':>5s} {'hidden-rule':>11s}  fingerprint(seed {seeds[0]})"
          f"  test tasks differing under other seeds")
    total_test = total_kept = 0
    summary = {}
    for uc in UCS:
        b = base[uc]
        kept = [t for t in b["test_ids"] if t not in excl.get(uc, {})]
        varying = sorted({t for s in seeds[1:] for t in b["test_ids"]
                          if runs[s][uc]["per_task"].get(t) != b["per_task"][t]})
        total_test += len(b["test_ids"])
        total_kept += len(kept)
        summary[uc] = dict(generated=b["generated"], test=len(b["test_ids"]), kept=len(kept),
                           test_with_hidden_rule=b["test_with_hidden_rule"], fingerprint=b["fingerprint"],
                           varying_with_seed=varying)
        print(f"{uc:20s} {b['generated']:9d} {len(b['test_ids']):5d} {len(kept):5d} {b['test_with_hidden_rule']:11d}  "
              f"{b['fingerprint']}  {len(varying)}" + (f" {varying[:6]}{' ...' if len(varying) > 6 else ''}" if varying else ""))
    print(f"{'nine use cases':20s} {'':9s} {total_test:5d} {total_kept:5d}")
    if a.json:
        json.dump(summary, open(a.json, "w"), indent=1)


if __name__ == "__main__":
    main()
