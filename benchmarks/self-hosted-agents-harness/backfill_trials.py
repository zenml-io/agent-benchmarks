"""Bring records written by older code up to date from jobs/ (nothing measured changes):
the per-trial list (with sandbox lifetimes), the sandbox cost estimate and total cost per
solved task. Run after a stream started with older code records a run."""
import json
import sys

sys.path.insert(0, ".")
import experiment as ex

rows = [json.loads(l) for l in open("attempts.jsonl") if l.strip()]
n = 0
for r in rows:
    d = ex.JOBS_DIR / r["job_name"]
    stale = "trials" not in r or any("wall_s" not in t for t in r["trials"]) or "sandbox_cost_est" not in r
    if not stale or not d.exists():
        continue
    j = ex.parse_job(d)
    if r.get("valid"):
        assert (j["attempted"], j["solved"]) == (r["attempted"], r["solved"]), r["job_name"]
    r["trials"] = j["trials"]
    r["sandbox_cost_est"] = ex.sandbox_cost(j["trials"])
    r["total_cost_per_solved"] = (round((r["cost"] + r["sandbox_cost_est"]) / r["solved"], 4)
                                  if r.get("cost") and r.get("solved") else None)
    n += 1
open("attempts.jsonl", "w").write("".join(json.dumps(r) + "\n" for r in rows))
print("updated", n)
