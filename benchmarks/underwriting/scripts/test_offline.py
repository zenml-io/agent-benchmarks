"""Offline checks of the ported harness: no model calls, no network.

  python scripts/test_offline.py      # needs the rebuilt environment (scripts/fetch_data.sh)

1. The six tools answer over the rebuilt database as the agent sees them (and read_query refuses writes).
2. The vendored price table reproduces the stored agent cost of every committed row from its token counts.
3. Endpoint configuration: open-weight keys resolve from OPENAI_COMPAT_* variables and fail clearly without them.
4. The simulated underwriter's prompt formats for every case.
"""
import glob
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "harness"))
import run as H  # noqa: E402
from llm import M  # noqa: E402

failures = []


def check(cond, msg):
    print(("ok   " if cond else "FAIL ") + msg)
    if not cond:
        failures.append(msg)


env = H.Env()
tables = json.loads(env.run("list_tables", {}))
check(len(tables) == 8, f"list_tables returns 8 tables ({len(tables)})")
rows = json.loads(env.run("read_query", {"query": "SELECT COUNT(*) AS n FROM appetite_guide"}))
check(rows[0]["n"] == 296514, f"appetite_guide has 296514 rows ({rows[0]['n']})")
check(env.run("read_query", {"query": "DELETE FROM lobs"}).startswith("Error"), "read_query refuses a DELETE")
check("***General***" in env.run("get_underwriting_guidelines", {}), "guidelines text is served")
check(json.loads(env.run("get_table_schema", {"table_name": "lobs"}))[1]["name"] == "lob", "get_table_schema works")
many = env.run("read_query", {"query": "SELECT * FROM naics"})
check(many.endswith("(first 200 rows shown)"), "read_query caps results at 200 rows")

n = bad = 0
for p in glob.glob(os.path.join(ROOT, "results", "runs", "*.jsonl")) + glob.glob(
        os.path.join(ROOT, "results", "tuned", "runs", "*.jsonl")):
    for line in open(p):
        r = json.loads(line)
        if r["status"] == "harness_error":
            continue
        n += 1
        bad += abs(M.cost(r["model"], r["input"], r["cached"], r["output"]) - r["cost"]) > 1e-9
check(n > 0 and bad == 0, f"price table reproduces the stored agent cost of {n} rows ({bad} differ)")

for k in ("OPENAI_COMPAT_BASE_URL_PROVIDER_A", "OPENAI_COMPAT_API_KEY_PROVIDER_A"):
    os.environ.pop(k, None)
try:
    M.endpoint("glm-5.3-flash@provider-a")
    check(False, "missing OPENAI_COMPAT_BASE_URL_PROVIDER_A raises")
except KeyError:
    check(True, "missing OPENAI_COMPAT_BASE_URL_PROVIDER_A raises KeyError (recorded as harness_error)")
os.environ["OPENAI_COMPAT_BASE_URL_PROVIDER_A"] = "https://example.invalid/v1/"
api, (base, key_env, auth), model = M.endpoint("glm-5.3-flash@provider-a")
check(base == "https://example.invalid/v1" and key_env == "OPENAI_COMPAT_API_KEY_PROVIDER_A" and auth == "Bearer "
      and model == "zai-org/GLM-5.3-Flash", "provider-a endpoint resolves from the environment")
check(M.endpoint("opus-5.5")[1][1] == "EVAL_ANTHROPIC_API_KEY", "Anthropic key variable is EVAL_ANTHROPIC_API_KEY")

tasks = json.load(open(os.path.join(ROOT, "env", "tasks.json")))
ok = 0
for t in tasks:
    c = t["company"]
    H.UNDERWRITER.format(seed=H.SEEDS[t["task"]], name=c["company name"], description=c["company description"],
                         lob=c["lob"], revenue=int(c["annual revenue"]), employees=c["number of employees"],
                         payroll=int(c["total payroll"]), vehicles=c["number of vehicles"],
                         construction=c["building construction"], state=c["state"])
    ok += 1
check(ok == 252, f"underwriter prompt formats for all {ok} cases")
print("all offline checks passed" if not failures else f"{len(failures)} check(s) failed")
sys.exit(1 if failures else 0)
