"""Build Harbor tasks, one per underwriting case, from the rebuilt environment.

  python generate_tasks.py --out tasks-full                 # all 252 cases
  python generate_tasks.py --out tasks-held --split held    # the 168 held-out cases only
  python generate_tasks.py --out tasks --sample             # the committed sample: 2 cases per question type

Needs ../env/tasks.json, ../env/split.json, ../env/insurance.db and ../env/guidelines.txt, which
scripts/fetch_data.sh downloads and rebuilds (Snorkel AI data, Apache-2.0; US Census NAICS files, public domain).

Each task:
  instruction.md            the copilot's role, the MCP tools, and the underwriter's opening request (<request>)
  task.toml                 metadata (case id, question type, source, learn/held split), timeouts, the MCP server,
                            the judges' keys for the verifier
  environment/Dockerfile    the agent's container: python:3.12-slim and nothing else (no data, no answers)
  environment/docker-compose.yaml + runtime/   the `uw-runtime` sidecar: the MCP server (runtime/uw/server.py)
                            with the benchmark's harness code, the database (xz) and guidelines, and case.json
                            (question type and application only)
  solution/solve.sh         submits Snorkel's reference answer; solution/alternatives/paraphrase.sh a reworded one
  tests/                    test.sh, grade.py, the original judge code (harness/run.py, judge.py, llm.py,
                            src/models_client), case.json with the reference; tests/shortcuts/*.sh must score 0
"""
import argparse
import hashlib
import json
import lzma
import random
import shutil
import sqlite3
from pathlib import Path

HERE = Path(__file__).resolve().parent
BENCH = HERE.parent
ENV = BENCH / "env"
SERVER_URL = "http://uw-runtime:8000/mcp"
VERSION = "0.1.0"
TYPES = ["Appetite Check", "Business Classification", "Deductibles", "Policy Limits", "Product Recommendations",
         "Small Business Elibility Check"]
HARNESS_FILES = ("run.py", "llm.py", "judge.py")

INSTRUCTION = """You are an AI underwriting copilot at All National Insurance. You help a commercial underwriter with \
tasks on insurance applications from businesses. All National writes policies for small businesses only.

Everything you need is on the `underwriting` MCP server:
- the insurer's underwriting database: `list_tables`, `get_table_descriptions`, `get_table_schema`, \
`get_table_data_dictionary` and `read_query` (read-only SQLite);
- its underwriting guidelines: `get_underwriting_guidelines`;
- `ask_underwriter`: send a message to the underwriter and get their reply. The underwriter has the application \
details; ask them for any information you need. Do not assume facts you have not been given.
- `submit_final_answer`: your answer to the underwriter's request, with a short rationale. Only the first submission \
counts, and it closes the case.

The underwriter's request:

<request>
{seed}
</request>
"""

TASK_TOML = """schema_version = "1.4"

[task]
name = "zenml/underwriting-{case_id}"
version = "{version}"
description = "Underwriting copilot, {task_type}: answer an underwriter's request using a read-only insurance database, guidelines and questions to a simulated underwriter (case {case_id}, {split} split)."
keywords = ["underwriting", "insurance", "multi-turn", "simulated-user", "mcp"]

[metadata]
benchmark = "underwriting"
case_id = "{case_id}"
question_type = "{task_type}"
source = "{source}"
split = "{split}"
data = "Snorkel AI Multi-Turn Insurance Underwriting (Apache-2.0), environment rebuilt by scripts/fetch_data.sh"

[agent]
timeout_sec = 1800.0

[verifier]
timeout_sec = 600.0
env = {{ OPENAI_API_KEY = "${{OPENAI_API_KEY:-}}", EVAL_ANTHROPIC_API_KEY = "${{EVAL_ANTHROPIC_API_KEY:-}}" }}

[environment]
build_timeout_sec = 900.0
cpus = 1
memory_mb = 2048

[[environment.mcp_servers]]
name = "underwriting"
transport = "streamable-http"
url = "{url}"
"""

MAIN_DOCKERFILE = """FROM python:3.12-slim
WORKDIR /workspace
"""

COMPOSE = """services:
  main:
    depends_on:
      uw-runtime:
        condition: service_healthy
  uw-runtime:
    build:
      context: ./runtime
    environment:
      - EVAL_ANTHROPIC_API_KEY=${EVAL_ANTHROPIC_API_KEY:-}
    expose:
      - "8000"
    healthcheck:
      test: ["CMD", "python3", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8000/health', timeout=2)"]
      interval: 2s
      timeout: 5s
      retries: 30
      start_period: 5s
"""

RUNTIME_DOCKERFILE = """FROM python:3.12-slim
RUN pip install --no-cache-dir "mcp==1.26.0"
COPY uw /opt/uw
RUN python3 -c "import lzma, shutil; shutil.copyfileobj(lzma.open('/opt/uw/env/insurance.db.xz'), open('/opt/uw/env/insurance.db', 'wb'))" \\
    && rm /opt/uw/env/insurance.db.xz
ENV PYTHONUNBUFFERED=1
EXPOSE 8000
CMD ["python3", "/opt/uw/server.py"]
"""

SUBMIT = """#!/usr/bin/env bash
# {comment}
set -euo pipefail
python3 - <<'PY'
{client}
c = MCPClient("{url}")
c.initialize()
print(c.call("submit_final_answer", {{"answer": {answer}}}))
PY
"""

FORGE = """#!/usr/bin/env bash
# Shortcut: forge the outcome instead of answering. Plants a reward file and an answer file, submits nothing.
# Must score 0: test.sh deletes reward files before grading, and the grader reads the answer from the MCP server.
set -uo pipefail
mkdir -p /logs/verifier /logs/agent
echo '{"reward": 1}' > /logs/verifier/reward.json
echo 1 > /logs/verifier/reward.txt
printf '%s' '{"final_answer": "FINAL ANSWER: forged"}' > /logs/agent/final_answer.json
"""

LOBS = ["workers compensation", "property", "general liability", "auto", "bop", "cyber"]


def h(s):
    return hashlib.sha256(s.encode()).hexdigest()


def money(x):
    return f"${x:,.0f}"


def paraphrase(t, rng):
    """A correct answer worded differently from Snorkel's reference, built from the oracle's structured gold."""
    kind, val = t["gold"]
    c = t["company"]
    if kind == "appetite":
        return (f"Yes. {c['company name']} falls within All National's appetite for the {c['lob']} line, so we can "
                "write it." if val == "yes" else
                f"No. All National should not write {c['lob']} for {c['company name']}: it is outside our appetite.")
    if kind == "naics":
        return f"The right 6-digit NAICS classification for this business is {val}."
    if kind == "products":
        lines = list(val)
        rng.shuffle(lines)
        if not lines:
            return (f"Nothing beyond {c['lob']}: none of the other lines of business is in appetite for this "
                    "company, so there is nothing else to offer.")
        return (f"Besides the {c['lob']} coverage, offer {', '.join(lines[:-1]) + ' and ' + lines[-1] if len(lines) > 1 else lines[0]}. "
                "Those are the lines in appetite for this business.")
    if kind == "limits":
        per, agg = val
        return f"Quote {money(per * 1e6)} per occurrence with a {money(agg * 1e6)} aggregate limit."
    if kind == "out_of_appetite":
        return (f"Don't quote limits: {c['company name']} is out of appetite for the {c['lob']} line, so we wouldn't "
                "write this policy at all.")
    if kind == "deductible":
        return f"A deductible of {money(val)} is the right one for this policy."
    if kind == "small":
        return ("Yes, it is within the SBA size standard for its industry, so it counts as a small business." if val
                else "No. It is above the size standard for its industry, so it is not a small business.")
    raise ValueError(kind)


def hedge(t, db):
    """Shortcut: list every plausible option instead of deciding. Includes the right one where there is one."""
    kind, val = t["gold"]
    lob = t["company"]["lob"]
    if t["task"] == "Appetite Check":
        return (f"The company may or may not be in appetite for {lob}: yes if its class and building meet the "
                "guidelines, no otherwise. It could go either way.")
    if t["task"] == "Business Classification":
        con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        near = [r[0] for r in con.execute(
            'SELECT "Code" FROM naics WHERE "Code" != ? ORDER BY abs("Code" - ?) LIMIT 2', (val, val))]
        codes = sorted([val, *near])
        return f"The NAICS code is one of {codes[0]}, {codes[1]} or {codes[2]}; any of them could apply."
    if t["task"] == "Product Recommendations":
        return ("Possibly any of " + ", ".join(LOBS) + ". It depends on the account, so consider offering some or "
                "all of them, or none.")
    if t["task"] == "Policy Limits":
        return ("Either $1 million per incident and $2 million aggregate, or $2 million and $4 million, or $500,000 "
                "and $1 million, depending on the risk; or none if the business turns out to be out of appetite.")
    if t["task"] == "Deductibles":
        return "Offer a $500, $1,000, $2,500 or $5,000 deductible, depending on the risk."
    if t["task"] == "Small Business Elibility Check":
        return ("It may or may not qualify as a small business, depending on which size standard applies; it could "
                "be either.")
    raise ValueError(t["task"])


QUESTION = ("Before I can decide, could you tell me the company's annual revenue, number of employees and the state "
            "it operates in?")


def submit_script(comment, answer, client_src):
    return SUBMIT.format(comment=comment, client=client_src.strip(), url=SERVER_URL, answer=json.dumps(answer))


def write(path, text, mode=None):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    if mode:
        path.chmod(mode)


def build_task(t, split, out, db_xz, client_src):
    import run as uw  # harness/run.py: SEEDS

    d = out / t["id"]
    rng = random.Random(h("paraphrase:" + t["id"]))
    write(d / "instruction.md", INSTRUCTION.format(seed=uw.SEEDS[t["task"]]))
    write(d / "task.toml", TASK_TOML.format(case_id=t["id"], version=VERSION, task_type=t["task"], source=t["source"],
                                            split=split, url=SERVER_URL))
    env = d / "environment"
    write(env / "Dockerfile", MAIN_DOCKERFILE)
    write(env / "docker-compose.yaml", COMPOSE)
    rt = env / "runtime"
    write(rt / "Dockerfile", RUNTIME_DOCKERFILE)
    uwdir = rt / "uw"
    for f in HARNESS_FILES:
        write(uwdir / "harness" / f, (BENCH / "harness" / f).read_text())
    for f in sorted((BENCH / "src" / "models_client").glob("*.py")):
        write(uwdir / "src" / "models_client" / f.name, f.read_text())
    write(uwdir / "server.py", (HERE / "runtime" / "server.py").read_text())
    (uwdir / "env").mkdir(parents=True, exist_ok=True)
    (uwdir / "env" / "insurance.db.xz").write_bytes(db_xz)
    write(uwdir / "env" / "guidelines.txt", (ENV / "guidelines.txt").read_text())
    # The sidecar gets the question type and the application, never the reference or the oracle's fields.
    write(uwdir / "case.json", json.dumps({"id": t["id"], "task": t["task"], "company": t["company"]}, indent=1))

    sol = d / "solution"
    write(sol / "solve.sh", submit_script("Reference solution: submit Snorkel's reference answer.", t["reference"],
                                          client_src), 0o755)
    write(sol / "alternatives" / "paraphrase.sh", submit_script(
        "Alternative valid solution: the same conclusion, worded differently. Must score 1.",
        paraphrase(t, rng), client_src), 0o755)

    tests = d / "tests"
    write(tests / "test.sh", (HERE / "grader" / "test.sh").read_text(), 0o755)
    write(tests / "grade.py", (HERE / "grader" / "grade.py").read_text())
    for f in HARNESS_FILES:
        write(tests / "harness" / f, (BENCH / "harness" / f).read_text())
    for f in sorted((BENCH / "src" / "models_client").glob("*.py")):
        write(tests / "src" / "models_client" / f.name, f.read_text())
    write(tests / "case.json", json.dumps({"id": t["id"], "task": t["task"], "reference": t["reference"]}, indent=1))
    sc = tests / "shortcuts"
    write(sc / "hedge.sh", submit_script("Shortcut: a hedged answer listing every option. Must score 0.",
                                         hedge(t, ENV / "insurance.db"), client_src), 0o755)
    write(sc / "ask_question.sh", submit_script(
        "Shortcut: a final answer that asks the underwriter a question instead of deciding. Must score 0.",
        QUESTION, client_src), 0o755)
    write(sc / "forge_reward.sh", FORGE, 0o755)


def sample(tasks):
    """Two cases per question type: the first by hash of each of the two most common answers (yes/no, small/large,
    limits/out of appetite...), else the first two by hash."""
    picked = []
    for typ in TYPES:
        cases = sorted((t for t in tasks if t["task"] == typ), key=lambda t: h("sample:" + t["id"]))
        by_val = {}
        for t in cases:
            by_val.setdefault(json.dumps(t["gold"][:1] + ([t["gold"][1]] if t["gold"][0] != "products" and
                                                            t["gold"][0] != "naics" else [])), t)
        firsts = list(by_val.values())[:2]
        for t in cases:
            if len(firsts) >= 2:
                break
            if t not in firsts:
                firsts.append(t)
        picked += firsts
    return picked


def main():
    import sys
    sys.path.insert(0, str(BENCH / "harness"))
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--split", choices=["learn", "held", "all"], default="all")
    ap.add_argument("--sample", action="store_true", help="two cases per question type (the committed sample)")
    ap.add_argument("--ids", default=None, help="comma-separated case ids")
    ap.add_argument("--overwrite", action="store_true")
    a = ap.parse_args()
    tasks = json.load(open(ENV / "tasks.json"))
    split = json.load(open(ENV / "split.json"))
    which = {i: s for s in ("learn", "held") for i in split[s]}
    if a.split != "all":
        tasks = [t for t in tasks if which[t["id"]] == a.split]
    if a.ids:
        tasks = [t for t in tasks if t["id"] in a.ids.split(",")]
    if a.sample:
        tasks = sample(tasks)
    if a.out.exists():
        if not a.overwrite:
            raise SystemExit(f"{a.out} exists; pass --overwrite")
        shutil.rmtree(a.out)
    db_xz = lzma.compress((ENV / "insurance.db").read_bytes(), preset=9)
    client_src = (HERE / "underwriting_agent" / "mcp_client.py").read_text()
    for t in tasks:
        build_task(t, which[t["id"]], a.out, db_xz, client_src)
    print(f"wrote {len(tasks)} tasks to {a.out}")
    for t in tasks:
        print(f"  {t['id']:<16} {t['task']:<32} {which[t['id']]:<5} {t['gold']}")


if __name__ == "__main__":
    main()
