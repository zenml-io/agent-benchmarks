"""Build the Harbor task that an arm runs in, for one SwapBench task.

  python scripts/build_harbor_task.py retail-refunds --visible <incumbent train results.json> [--arm 1]

Writes swapbench/harbor/<task>-arm<N>/ (gitignored, rebuildable):
  instruction.md, task.toml, environment/{Dockerfile, strip_hidden.py, app/...}, tests/test.sh

The sandbox gets the production agent (tau2 at a pinned commit) with every copy of the hidden
scenarios removed: retail test tasks, voice variants, per-task issue notes, git history and tau2's
published result files. While the agent runs, the network is limited to the two model APIs and PyPI.
"""
import argparse
import json
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

import yaml  # noqa: E402

from swapbench import pricing, trace  # noqa: E402

DOCKERFILE = """FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends git curl tmux asciinema procps \\
    && rm -rf /var/lib/apt/lists/*
RUN git init -q /opt/tau2 && cd /opt/tau2 && git remote add origin {repo} \\
    && git fetch -q --depth 1 origin {commit} && git checkout -q FETCH_HEAD \\
    && rm -rf .git .github web docs/leaderboard data/tau2/results data/voice
{scenarios}COPY strip_hidden.py /tmp/strip_hidden.py
RUN python /tmp/strip_hidden.py /opt/tau2 {domain} && rm /tmp/strip_hidden.py \\
    && cd /opt/tau2 && pip install --no-cache-dir -e . websockets pyyaml
COPY app/ /app/
{tools}WORKDIR /app
"""

STRIP = '''"""Remove every hidden scenario of <domain> from the tau2 tree (keeps only the visible split)."""
import json, os, shutil, sys
root, domain = sys.argv[1], sys.argv[2]
d = os.path.join(root, "data", "tau2", "domains", domain)
split = json.load(open(os.path.join(d, "split_tasks.json")))
visible = set(split["train"]) | set(split.get("pool", []))  # ids may be numeric or generated ("g12", "p3")
tasks = [t for t in json.load(open(os.path.join(d, "tasks.json"))) if t["id"] in visible]
json.dump(tasks, open(os.path.join(d, "tasks.json"), "w"), indent=1)
order = lambda i: (0, int(i)) if i.isdigit() else (1, i)
out = {"train": sorted(split["train"], key=order), "base": sorted(visible, key=order)}
if split.get("pool"):
    out["pool"] = sorted(split["pool"], key=order)
json.dump(out, open(os.path.join(d, "split_tasks.json"), "w"), indent=1)
for extra in ("tasks_voice.json", "task_issues", "audio_difficulty.json"):
    p = os.path.join(d, extra)
    if os.path.isdir(p):
        shutil.rmtree(p)
    elif os.path.exists(p):
        os.remove(p)
print("kept", len(tasks), "visible scenarios")
'''

TEST_SH = """#!/bin/bash
# Collects the submission; grading against the hidden set happens outside the sandbox (swapbench.grade).
mkdir -p /logs/verifier
echo "===SWAPBENCH-CONFIG==="; cat /app/submission/config.yaml 2>/dev/null; echo "===SWAPBENCH-VERDICT==="
cat /app/submission/verdict.json 2>/dev/null; echo "===SWAPBENCH-END==="
python - <<'P'
import json, yaml
ok = 0
try:
    c = yaml.safe_load(open("/app/submission/config.yaml")); v = json.load(open("/app/submission/verdict.json"))
    ok = int(bool(c.get("model")) and v.get("decision") in ("SAFE", "UNSAFE", "INSUFFICIENT_EVIDENCE"))
except Exception as e:
    print("invalid submission:", e)
open("/logs/verifier/reward.txt", "w").write(str(ok))
P
"""

SOLVE_SH = """#!/bin/bash
# Validation only (Harbor's oracle agent): checks isolation, key injection and replay, then submits a
# trivial config. Arms never see this file.
curl -s -m 10 -o /dev/null -w "github:%{http_code}\\n" https://github.com/sierra-research/tau2-bench || echo "github: blocked"
curl -s -m 10 -o /dev/null -w "openai:%{http_code}\\n" https://api.openai.com/v1/models -H "Authorization: Bearer $OPENAI_API_KEY"
python -c "import json;print('hidden scenarios on disk:', len(json.load(open('/opt/tau2/data/tau2/domains/retail/tasks.json'))))"
cd /opt/tau2 && timeout 600 tau2 run -d retail --agent-llm gpt-5-mini-2025-08-07 --agent-llm-args '{}' \\
  --user-llm anthropic/claude-haiku-5-5 --user-llm-args '{}' --task-split-name train --num-tasks 1 \\
  --save-to /tmp/oracle_check --log-level ERROR 2>&1 | grep -E "Average Reward|Cost/Conv|Error" | head -5
mkdir -p /app/submission
printf 'model: gpt-5-mini-2025-08-07\\nllm_args: {}\\npolicy_suffix: ""\\n' > /app/submission/config.yaml
echo '{"decision": "INSUFFICIENT_EVIDENCE", "evidence": "oracle validation run"}' > /app/submission/verdict.json
"""

TASK_TOML = """version = "1.0"

[metadata]
author_name = "swapbench"
difficulty = "hard"
category = "model-migration"
tags = ["swapbench", "{name}", "arm{arm}"]

[agent]
timeout_sec = {timeout}
network_mode = "allowlist"
allowed_hosts = ["api.openai.com", "api.anthropic.com", "pypi.org", "files.pythonhosted.org"]

# Agents get the keys through `harbor run --ae 'KEY=${{VAR}}'` (scripts/run_arm.sh); the oracle through this:
[solution.env]
OPENAI_API_KEY = "${{OPENAI_API_KEY}}"
ANTHROPIC_API_KEY = "${{EVAL_ANTHROPIC_API_KEY}}"

[verifier]
timeout_sec = 300.0

[environment]
build_timeout_sec = 1800.0
cpus = 4
memory = "8G"
storage = "10G"
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("task")
    ap.add_argument("--visible", required=True, help="incumbent results.json on the visible split")
    ap.add_argument("--arm", type=int, default=1)
    ap.add_argument("--data-dir", help="generated TAU2_DATA_DIR; only its visible scenarios are copied in")
    ap.add_argument("--pool-dir", help="arm 2: generated data dir whose 'pool' split is shipped as extra unlabeled scenarios")
    a = ap.parse_args()
    tdir = os.path.join(ROOT, "tasks", a.task)
    spec = yaml.safe_load(open(os.path.join(tdir, "task.yaml")))
    out = os.path.join(ROOT, "harbor", f"{a.task}-arm{a.arm}")
    shutil.rmtree(out, ignore_errors=True)
    env = os.path.join(out, "environment")
    app = os.path.join(env, "app")
    os.makedirs(os.path.join(app, "submission"))
    os.makedirs(os.path.join(out, "tests"))
    instr = open(os.path.join(tdir, "instruction.md")).read()
    if a.arm == 2:
        instr += open(os.path.join(ROOT, "tools", "ARM2_INSTRUCTION.md")).read()
    open(os.path.join(out, "instruction.md"), "w").write(instr)
    src = spec["source"]
    scen, tools = "", ""
    if a.arm == 2:  # the verification toolkit: sb CLI + the stats/adapter modules it uses (no scenario generator)
        sbd = os.path.join(env, "sb")
        os.makedirs(os.path.join(sbd, "swapbench"))
        shutil.copy(os.path.join(ROOT, "tools", "sb.py"), sbd)
        for m in ("__init__.py", "stats.py", "tau2_adapter.py", "pricing.py"):
            shutil.copy(os.path.join(ROOT, "swapbench", m), os.path.join(sbd, "swapbench", m))
        tools = ("COPY sb/ /opt/sb/\nRUN printf '#!/bin/sh\\nexec python /opt/sb/sb.py \"$@\"\\n' > /usr/local/bin/sb "
                 "&& chmod +x /usr/local/bin/sb\n")
    if a.data_dir:  # generated scenarios: ship only the visible split
        dom = os.path.join(a.data_dir, "tau2", "domains", src["domain"])
        vis = json.load(open(os.path.join(dom, "split_tasks.json")))[spec["sets"]["visible"]["split"]]
        tasks = [t for t in json.load(open(os.path.join(dom, "tasks.json"))) if t["id"] in vis]
        os.makedirs(os.path.join(env, "scenarios"))
        json.dump(tasks, open(os.path.join(env, "scenarios", "tasks.json"), "w"), indent=1)
        split = {"train": vis, "base": vis}
        if a.pool_dir:
            pdom = os.path.join(a.pool_dir, "tau2", "domains", src["domain"])
            pool = json.load(open(os.path.join(pdom, "tasks.json")))
            tasks += pool
            split["pool"] = [t["id"] for t in pool]
            split["base"] = vis + split["pool"]
            json.dump(tasks, open(os.path.join(env, "scenarios", "tasks.json"), "w"), indent=1)
        json.dump(split, open(os.path.join(env, "scenarios", "split_tasks.json"), "w"), indent=1)
        scen = f"COPY scenarios/ /opt/tau2/data/tau2/domains/{src['domain']}/\n"
    open(os.path.join(env, "Dockerfile"), "w").write(
        DOCKERFILE.format(repo=src["repo"], commit=src["commit"], domain=src["domain"], scenarios=scen, tools=tools))
    open(os.path.join(env, "strip_hidden.py"), "w").write(STRIP)
    open(os.path.join(out, "tests", "test.sh"), "w").write(TEST_SH)
    os.chmod(os.path.join(out, "tests", "test.sh"), 0o755)
    os.makedirs(os.path.join(out, "solution"))
    open(os.path.join(out, "solution", "solve.sh"), "w").write(SOLVE_SH)
    os.chmod(os.path.join(out, "solution", "solve.sh"), 0o755)
    hours = spec["budget"]["wall_hours"]
    open(os.path.join(out, "task.toml"), "w").write(TASK_TOML.format(name=a.task, arm=a.arm, timeout=float(hours * 3600)))
    prices = {m: dict(zip(("input", "cached_input", "output"), pricing.PRICES[pricing.canonical(m)]))
              for m in spec["allowed_models"]}
    json.dump(prices, open(os.path.join(app, "prices.json"), "w"), indent=1)
    n = trace.convert(a.visible, os.path.join(app, "traces", "visible"), "visible", a.task, "retail-support-agent",
                      src["domain"])
    open(os.path.join(app, "submission", ".keep"), "w").close()
    print(f"built {out} with {n} visible traces")


if __name__ == "__main__":
    main()
