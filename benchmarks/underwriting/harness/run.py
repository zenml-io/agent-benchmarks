"""Run one model as the underwriting copilot on the validated tasks.

  python harness/run.py <model_key> [--n 252] [--offset 0] [--workers 8] [--ids a,b]

Setup, mirroring Snorkel's (as described in its dataset card and visible in its traces):
- The copilot has six tools over the rebuilt environment: list_tables, get_table_descriptions, get_table_schema,
  get_table_data_dictionary, read_query (read-only SQL) and get_underwriting_guidelines. Outputs and error messages
  follow the recorded formats. Snorkel's system prompt is not published; ours is below.
- A simulated underwriter (Claude Haiku 5.5) holds the application data, opens with the task's request, and answers
  the copilot's questions from that data only. Its cost is environment cost, reported apart from the agent's.
- The episode ends at a message containing "FINAL ANSWER:", or at 30 copilot calls / 12 underwriter turns. An empty
  copilot turn gets "Please continue." (at most twice) for every model.
- Grading: harness/judge.py with two judges (GPT-6 Luna, Claude Haiku 5.5); GPT-6.1 Sol breaks ties.
One JSON line per task in results/runs/<model>.jsonl (reruns skip finished tasks) and the full transcript in
results/transcripts/<model>/<task>.json.
"""
import argparse
import hashlib
import json
import os
import re
import sqlite3
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from judge import grade  # noqa: E402
from llm import M, call_model, complete  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENV = os.path.join(ROOT, "env")
SIMULATOR = "haiku-5.5"
JUDGES, TIEBREAK = ("gpt-6-luna", "haiku-5.5"), "gpt-6.1-sol"
MAX_CALLS, MAX_TURNS, MAX_ROWS = 30, 12, 200

DESCRIPTIONS = {
    "naics": "table with 2022 6-digit NAICS codes",
    "naics_2digit": "table with 2022 2-digit NAICS codes",
    "naics_2022_2017": "table that maps 2022 NAICS codes to 2017 NAICS codes",
    "naics_2012_2017": "table that maps 2012 NAICS codes to 2017 NAICS codes",
    "small_business_definition": "table that defines what a 'small' business is by its 6-digit 2012 NAICS code and "
                                 "annual revenue in US dollars",
    "lobs": "table of lines of business being offered for small businesses",
    "states": "table of US state names and abbreviations",
    "appetite_guide": "table that defines appetite for writing a policy for a small business depending on features "
                      "of the business such as business classification",
}
DICTIONARIES = {  # as returned by get_table_data_dictionary in the traces (states, naics_2022_2017 written to match)
    "small_business_definition": {
        "NAICS Codes": "6-digit 2012 NAICS code",
        "Size Standards in millions of dollars": "Maximum possible annual revenue (in millions of US dollars) for a "
        "business with that NAICS code in order for it to be considered a 'small' business.",
        "Size standards in number of employees": "Maximum number of employees for a business with that NAICS code in "
        "order for it to be considered a 'small' business."},
    "lobs": {"lob": "lob"},
    "appetite_guide": {"naics": "2022 naics code", "state": "state abbreviation", "lob": "line of business",
                       "appetite": "whether the business is in appetite, out of appetite or 'qualified' depending on "
                                   "other features."},
    "naics": {"Code": "6-digit 2022 NAICS code", "Title": "Title of each 2022 NAICS code",
              "Description": "More granular description of the 2022 NAICS code."},
    "naics_2digit": {"Code": "6-digit 2022 NAICS code", "Title": "Title of each 2022 NAICS code",
                     "Description": "More granular description of the 2022 NAICS code."},
    "naics_2012_2017": {"2012 NAICS": "6-digit 2012 NAICS code", "2017 NAICS": "6-digit 2017 NAICS code"},
    "naics_2022_2017": {"2022 NAICS": "6-digit 2022 NAICS code", "2017 NAICS": "6-digit 2017 NAICS code"},
    "states": {"State": "US state name", "Abbreviation": "two-letter state abbreviation"},
}


def fn(name, desc, props=None, required=()):
    return {"type": "function", "function": {"name": name, "description": desc, "parameters": {
        "type": "object", "properties": props or {}, "required": list(required)}}}


TOOLS = [
    fn("list_tables", "List the tables in the underwriting database."),
    fn("get_table_descriptions", "Get a short description of every table in the database."),
    fn("get_table_schema", "Get the columns and types of a table.",
       {"table_name": {"type": "string"}}, ["table_name"]),
    fn("get_table_data_dictionary", "Get the meaning of each column of a table.",
       {"table": {"type": "string"}}, ["table"]),
    fn("read_query", "Run a read-only SQL (SQLite) SELECT query against the database and get the rows as JSON.",
       {"query": {"type": "string"}}, ["query"]),
    fn("get_underwriting_guidelines", "Get All National Insurance's underwriting guidelines."),
]

SYSTEM = """You are an AI underwriting copilot at All National Insurance. You help a commercial underwriter with tasks
on insurance applications from businesses. All National writes policies for small businesses only.

Use your tools to consult the insurer's underwriting database (list_tables, get_table_descriptions, get_table_schema,
get_table_data_dictionary, read_query) and its underwriting guidelines (get_underwriting_guidelines). The underwriter
has the application details; ask them for any information you need. Do not assume facts you have not been given.

When you have the answer, reply with a message that starts with "FINAL ANSWER:" followed by your answer and a short
rationale. Use "FINAL ANSWER:" only once, in that last message: it ends the conversation. Questions to the underwriter
are ordinary messages without it."""

SEEDS = {
    "Appetite Check": "Hi, I need help determining whether a company applying for insurance for a specific LOB is in "
                      "appetite.",
    "Product Recommendations": "Hi, I'd like to figure out what other insurance products, or LOBs, I should offer "
                               "this company.",
    "Policy Limits": "What policy limits should I offer this company for this LOB?",
    "Small Business Elibility Check": "Hi, I need help determining whether a company qualifies as a 'small "
                                      "business'.",
    "Deductibles": "What policy deductible should I offer this company for this LOB?",
    "Business Classification": "Hi, I need help finding the correct 6-digit NAICS classification code for this "
                               "company.",
}

UNDERWRITER = """You are a commercial insurance underwriter at All National Insurance, working with an AI copilot.
Your request to the copilot was: "{seed}"

The application you are working on:
- Company name: {name}
- Description: {description}
- Line of business (LOB) in question: {lob}
- Annual revenue: ${revenue:,}
- Number of employees: {employees}
- Total annual payroll: ${payroll:,}
- Number of vehicles: {vehicles}
- Building construction: {construction}
- State: {state}

How to behave:
- Answer the copilot's questions using only the application above. When a message asks several things, answer
  every part you can and say you don't know only for the parts the application does not cover (for example a NAICS
  code, prior policies or loss history). Always write the information itself out in full; never reply with an
  introduction such as "Here is the description:" without the description.
  Example: asked "What is the NAICS code, the state, and the annual revenue?", reply "I don't have a NAICS code. The
  company is in Ohio, with annual revenue of $4,200,000."
- Do not do the copilot's job: never name a NAICS code or decide appetite, small-business status, limits,
  deductibles or other products yourself, and never say what the answer is.
- Keep each reply to one to three sentences, in plain words, as a busy underwriter would."""


class Env:
    def __init__(self):
        self.db_path = os.path.join(ENV, "insurance.db")
        self.guidelines = open(os.path.join(ENV, "guidelines.txt")).read()
        self.tables = list(DESCRIPTIONS)

    def run(self, name, args):
        try:
            if name == "list_tables":
                return json.dumps(sorted(self.tables))
            if name == "get_table_descriptions":
                return json.dumps(DESCRIPTIONS)
            if name == "get_underwriting_guidelines":
                return self.guidelines
            if name == "get_table_data_dictionary":
                t = args.get("table") or args.get("table_name")
                if t not in DICTIONARIES:
                    return f"Error: ToolException('Unknown table: {t}')\n Please fix your mistakes."
                return json.dumps(DICTIONARIES[t])
            con = sqlite3.connect(f"file:{self.db_path}?mode=ro", uri=True)
            con.row_factory = sqlite3.Row
            if name == "get_table_schema":
                t = args.get("table_name") or args.get("table")
                rows = [dict(r) for r in con.execute(f"PRAGMA table_info(\"{t}\")")]
                if not rows:
                    return f"Error: ToolException('Error executing tool get_table_schema: no such table: {t}')\n " \
                           "Please fix your mistakes."
                return json.dumps([{k: r[k] for k in ("cid", "name", "type", "notnull", "dflt_value", "pk")}
                                   for r in rows])
            if name == "read_query":
                q = str(args.get("query", "")).strip()
                if not re.match(r"(?is)^\s*(select|with)\b", q):
                    return "Error: ToolException('Error executing tool read_query: Only SELECT queries are " \
                           "allowed.')\n Please fix your mistakes."
                rows = [dict(r) for r in con.execute(q).fetchmany(MAX_ROWS + 1)]
                note = f"\n(first {MAX_ROWS} rows shown)" if len(rows) > MAX_ROWS else ""
                return json.dumps(rows[:MAX_ROWS]) + note
            return f"Error: unknown tool {name}"
        except sqlite3.Error as e:
            return f"Error: ToolException('Error executing tool {name}: SQLite error: {e}')\n Please fix your mistakes."


def underwriter_reply(task, transcript):
    c = task["company"]
    system = UNDERWRITER.format(
        seed=SEEDS[task["task"]], name=c["company name"], description=c["company description"], lob=c["lob"],
        revenue=int(c["annual revenue"]), employees=c["number of employees"], payroll=int(c["total payroll"]),
        vehicles=c["number of vehicles"], construction=c["building construction"], state=c["state"])
    # From the underwriter's side, the copilot's messages are the other party.
    msgs = [{"role": "user" if who == "copilot" else "assistant", "content": text} for who, text in transcript]
    text, usage, cost = complete(SIMULATOR, system, msgs, max_tokens=600)
    return text.strip() or "I don't know.", cost


def run_task(env, key, task):
    msgs = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": SEEDS[task["task"]]}]
    transcript = [("underwriter", SEEDS[task["task"]])]
    calls, failures, tool_calls = [], [], 0
    sim_cost, final, status = 0.0, None, "unfinished"
    t0 = time.time()
    turns = nudges = 0
    for _ in range(MAX_CALLS):
        try:
            msg, usage, lat, retries = call_model(key, msgs, TOOLS)
        except RuntimeError as e:
            failures.append(str(e).split()[0])
            calls.append(dict(error=str(e)[:300]))
            status = failures[-1]
            break
        calls.append(dict(**usage, latency=round(lat, 3), retries=retries))
        tcs = msg.get("tool_calls") or []
        text = msg.get("content") or ""
        if not tcs and not text.strip():
            # An empty turn (seen with GPT-6.1 Sol after reasoning is passed back) gets the same nudge for every model,
            # at most twice; a third empty turn ends the episode as unresolved.
            nudges += 1
            if nudges <= 2:
                msgs.append({"role": "user", "content": "Please continue."})
                continue
            failures.append("empty_reply")
            status = "empty_reply"
            break
        keep_rz = "gpt-oss" in key and msg.get("reasoning_content")
        msgs.append({"role": "assistant", "content": text or None, **({"tool_calls": tcs} if tcs else {}),
                     **({"reasoning_content": msg["reasoning_content"]} if keep_rz else {}),
                     **({"_items": msg["_items"]} if msg.get("_items") else {})})
        if text.strip():
            transcript.append(("copilot", text))
        if m := re.search(r"FINAL ANSWER\s*:", text):
            final, status = text[m.start():], "finished"
            break
        if tcs:
            for tc in tcs:
                tool_calls += 1
                try:
                    args = json.loads(tc["function"].get("arguments") or "{}")
                    out = env.run(tc["function"]["name"], args if isinstance(args, dict) else {})
                except json.JSONDecodeError:
                    failures.append("tool_parse_error")
                    out = "Error: arguments were not valid JSON."
                msgs.append({"role": "tool", "tool_call_id": tc["id"], "content": out[:20000]})
            continue
        turns += 1
        if turns > MAX_TURNS:
            failures.append("turn_limit")
            status = "turn_limit"
            break
        reply, c = underwriter_reply(task, transcript)
        sim_cost += c
        transcript.append(("underwriter", reply))
        msgs.append({"role": "user", "content": reply})
    else:
        failures.append("step_limit")
        status = "step_limit"
    verdicts, judge_cost = [], 0.0
    if final:
        for j in JUDGES:
            ok, reason, c = grade(j, task["task"], task["reference"], final)
            verdicts.append((j, ok, reason))
            judge_cost += c
        if len({v[1] for v in verdicts}) > 1 or None in {v[1] for v in verdicts}:
            ok, reason, c = grade(TIEBREAK, task["task"], task["reference"], final)
            verdicts.append((TIEBREAK, ok, reason))
            judge_cost += c
    success = bool(final) and bool(verdicts[-1][1] if len(verdicts) == 3 else verdicts[0][1])
    inp = sum(c.get("input", 0) for c in calls)
    cached = sum(c.get("cached", 0) for c in calls)
    out = sum(c.get("output", 0) for c in calls)
    return dict(task=task["id"], task_type=task["task"], source=task["source"], model=key, success=success,
                status=status, failures=failures, calls=len(calls), tool_calls=tool_calls,
                underwriter_turns=turns, input=inp, cached=cached, output=out,
                reasoning=sum(c.get("reasoning", 0) for c in calls), cost=M.cost(key, inp, cached, out),
                sim_cost=sim_cost, judge_cost=judge_cost, latency=round(time.time() - t0, 2),
                call_latencies=[c.get("latency") for c in calls], errors=[c["error"] for c in calls if "error" in c],
                final_answer=final, verdicts=verdicts, ts=time.time()), {
                "task": task["id"], "model": key, "system": SYSTEM, "tools": TOOLS,
                "messages": [{k: v for k, v in m.items() if not k.startswith("_")} for m in msgs],
                "calls": calls, "transcript": transcript}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("model")
    ap.add_argument("--n", type=int, default=1000)
    ap.add_argument("--offset", type=int, default=0)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--ids", default=None)
    ap.add_argument("--arm", default=None, help="tuned-harness arm name; writes to results/tuned/")
    ap.add_argument("--effort", default=None, help="effort / reasoning effort level for the agent's calls")
    ap.add_argument("--prompt", default=None, help="file with a system prompt replacing SYSTEM")
    ap.add_argument("--split", default=None, choices=["learn", "held"], help="only tasks in this half of env/split.json")
    a = ap.parse_args()
    global SYSTEM
    if a.prompt:
        SYSTEM = open(a.prompt).read().strip()
    if a.effort:
        from models_client import client as shared  # the vendored client, already imported by llm.py
        shared.EXTRA.update(anthropic={"output_config": {"effort": a.effort}},
                            responses={"reasoning": {"effort": a.effort}},
                            chat={"reasoning_effort": a.effort})
    tasks = json.load(open(os.path.join(ENV, "tasks.json")))
    if a.split:
        keep = set(json.load(open(os.path.join(ENV, "split.json")))[a.split])
        tasks = [t for t in tasks if t["id"] in keep]
    # A fixed sample that mixes task types and sources: order by a hash of the task id.
    tasks = sorted(tasks, key=lambda t: hashlib.sha256(t["id"].encode()).hexdigest())
    tasks = [t for t in tasks if t["id"] in a.ids.split(",")] if a.ids else tasks[a.offset:a.offset + a.n]
    base = os.path.join(ROOT, "results", "tuned") if a.arm else os.path.join(ROOT, "results")
    name = f"{a.model}__{a.arm}" if a.arm else a.model
    out = os.path.join(base, "runs", f"{name}.jsonl")
    tdir = os.path.join(base, "transcripts", name)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    os.makedirs(tdir, exist_ok=True)
    done = set()
    if os.path.exists(out):
        for line in open(out):
            r = json.loads(line)
            if r["status"] not in ("api_error", "account_blocked", "timeout"):
                done.add(r["task"])
    todo = [t for t in tasks if t["id"] not in done]
    print(f"{a.model}: {len(todo)} to run ({len(done)} done)", flush=True)
    env, lock = Env(), threading.Lock()

    def one(t):
        try:
            row, transcript = run_task(env, a.model, t)
        except Exception as e:  # noqa: BLE001 - a crashed task is recorded, not lost
            row, transcript = dict(task=t["id"], task_type=t["task"], source=t["source"], model=a.model,
                                   success=False, status="harness_error", failures=["harness_error"],
                                   errors=[repr(e)[:300]], cost=0.0, sim_cost=0.0, judge_cost=0.0, ts=time.time()), None
        with lock:
            with open(out, "a") as f:
                f.write(json.dumps(row) + "\n")
            if transcript:
                json.dump(transcript, open(os.path.join(tdir, f"{t['id']}.json"), "w"))

    with ThreadPoolExecutor(a.workers) as ex:
        list(ex.map(one, todo))
    rows = [json.loads(line) for line in open(out)]
    n = len(rows)
    print(f"done: {n} tasks, success {sum(r['success'] for r in rows) / max(n, 1):.1%}, agent ${sum(r['cost'] for r in rows):.3f}, "
          f"underwriter ${sum(r.get('sim_cost', 0) for r in rows):.3f}, judge ${sum(r.get('judge_cost', 0) for r in rows):.3f}",
          flush=True)


if __name__ == "__main__":
    main()
