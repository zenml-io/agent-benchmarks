"""Build results/tau2-telecom-public-traces.json from existing results only (no model calls).

  uv run python scripts/build_tau2_public.py [--step-check-dir DIR] [--out FILE]      # from benchmarks/tau2-telecom

Inputs (paths relative to benchmarks/tau2-telecom):
- data/*.parquet: Exgentic/agent-llm-traces-v2 shards (git-ignored; scripts/fetch_data.py)
- results/runs/step_check/out{,_responses}/{report.json,calls.jsonl}: the Kitaru model-swap step check
  (stripped copies, scripts/strip_step_check.py; a fresh swap_run.py output directory works too)
- results/costs/public_traces_step_check.json: recorded spend
Paired step-check intervals use scripts/stats.py paired_delta (cluster bootstrap over recorded runs).
"""
import argparse
import glob
import json
import os
import re
import sys
from collections import Counter, defaultdict
from decimal import ROUND_HALF_EVEN, Decimal

import pyarrow.parquet as pq

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # benchmarks/tau2-telecom
sys.path.insert(0, os.path.join(HERE, "scripts"))
from stats import paired_delta  # noqa: E402

# Text in the export names the original location and commit (provenance), not this copy.
BENCH = "benchmarks/tau2-telecom-public"
ORIGINAL_COMMIT = "c2bb92e93b865db6ae686adff8bc0281a79c4d31"
STEP_CHECK_DIR = os.path.join(HERE, "results", "runs", "step_check")
COSTS = os.path.join(HERE, "results", "costs", "public_traces_step_check.json")
OUT = os.path.join(HERE, "results", "tau2-telecom-public-traces.json")
SLUG = "tau2-telecom-public-traces"
HARNESS = "tool_calling"
BENCHMARK = "tau2_telecom"
STEP_DIRS = ["out", "out_responses"]  # batch 2 supersedes batch 1 for gpt-5.6-sol and gpt-5.6-luna
TYPE_RULES = [  # first match wins, applied to the simulated user's first three messages (text matching)
    ("mms", r"\bmms\b|picture message|multimedia"),
    ("mobile_data", r"mobile data|internet|data connection|\bdata\b.*(slow|not working|work)|speed"),
    ("no_service", r"no service|no signal|can.?t make (phone )?calls|no bars|service (is|has) (down|out)"),
]
NO_DEVICE_ACCESS = re.compile(r"(do not|don't|cannot|can't) have access to (the )?(device|your device|device tools)", re.I)
TRANSFER = "transfer_to_human_agents"
EXACT = {"same_tool_same_args", "same_text"}
SAME_TOOL = {"same_tool_same_args", "same_tool_different_args"}

VENDOR = {"DeepSeek-V3.2": "DeepSeek", "Kimi-K2.5": "Moonshot AI", "claude-opus-4-5": "Anthropic",
          "gemini-3-pro-preview": "Google", "gpt-5.2-2025-12-11": "OpenAI"}
DISPLAY = {"DeepSeek-V3.2": "DeepSeek V3.2", "Kimi-K2.5": "Kimi K2.5", "claude-opus-4-5": "Claude Opus 4.5",
           "gemini-3-pro-preview": "Gemini 3 Pro (preview)", "gpt-5.2-2025-12-11": "GPT-5.2"}
OPEN = {"DeepSeek-V3.2", "Kimi-K2.5"}
CANDIDATE_INFO = {  # step-check candidates: display name, vendor, weights
    "gpt-5.2-2025-12-11": ("GPT-5.2", "OpenAI", "closed"),
    "gpt-5.6-sol": ("GPT-5.6 Sol", "OpenAI", "closed"),
    "gpt-5.6-luna": ("GPT-5.6 Luna", "OpenAI", "closed"),
    "gpt-5.4-mini": ("GPT-5.4 mini", "OpenAI", "closed"),
    "deepseek-ai/DeepSeek-V4.1-Flash": ("DeepSeek V4.1 Flash", "DeepSeek", "open"),
    "moonshotai/Kimi-K3": ("Kimi K3", "Moonshot AI", "open"),
    "zai-org/GLM-5.3": ("GLM-5.3", "Z.ai", "open"),
    "Qwen/Qwen3.8-27B": ("Qwen3.8 27B", "Alibaba Qwen", "open"),
}


def q4(x):
    return float(Decimal(str(x)).quantize(Decimal("0.0001"), rounding=ROUND_HALF_EVEN))


def wilson(k, n, z=1.96):
    """Same formula as benchmarks/haiku-tax/calib/analyze.py and the other exporters."""
    if n == 0:
        return None
    p = k / n
    c = z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5) / (1 + z * z / n)
    m = (p + z * z / (2 * n)) / (1 + z * z / n)
    return [q4(m - c), q4(m + c)]


def load_runs():
    rows, total, telecom = [], 0, Counter()
    for path in sorted(glob.glob(os.path.join(HERE, "data", "*.parquet"))):
        # Count every row from two small columns; load full rows (with spans) for the kept slice only.
        meta = pq.read_table(path, columns=["benchmark", "harness"])
        total += meta.num_rows
        for b, h in zip(meta["benchmark"].to_pylist(), meta["harness"].to_pylist()):
            if b == BENCHMARK:
                telecom[h] += 1
        rows += pq.read_table(path, filters=[("benchmark", "=", BENCHMARK), ("harness", "=", HARNESS)]).to_pylist()
    return rows, total, telecom


def turns(run):
    """Agent outputs in order: ('call', name, args) or ('say', None, text)."""
    out = []
    for s in sorted(run["spans"], key=lambda s: s["start_time"]):
        for m in json.loads(s["attributes"]["gen_ai.output.messages"] or "[]"):
            for p in m.get("parts", []):
                if p.get("type") == "tool_call":
                    out.append(("call", p.get("name"), p.get("arguments")))
                elif p.get("type") == "text":
                    out.append(("say", None, p.get("content") or ""))
    return out


def user_messages(run):
    last = sorted(run["spans"], key=lambda s: s["start_time"])[-1]
    msgs = json.loads(last["attributes"]["gen_ai.input.messages"])
    texts = [p.get("content", "") for m in msgs if m.get("role") == "user" for p in m.get("parts", [])
             if p.get("type") == "text"]
    return texts[1:]  # the first user message carries the agent policy


def issue_type(run):
    text = " ".join(user_messages(run)[:3]).lower()
    for name, pattern in TYPE_RULES:
        if re.search(pattern, text):
            return name
    return "unclassified"


def run_model(run):
    """The model that answered the run's spans (two rows carry another model's config_path)."""
    models = {s["attributes"].get("gen_ai.request.model") for s in run["spans"]}
    return models.pop() if len(models) == 1 else run["models"][0]


def failure_category(run, tr):
    if run["success"]:
        return None
    return "escalated_to_human_on_unsolved_task" if any(n == TRANSFER for k, n, _ in tr if k == "call") \
        else "ended_unsolved_without_escalation"


def git_commit(path):
    """The original repository commit that added this benchmark (the published copy is not a git checkout of it)."""
    return ORIGINAL_COMMIT


def step_check():
    """Merge the step-check batches: per candidate, take the last batch where it answered any call."""
    reports, calls = {}, defaultdict(list)
    for d in STEP_DIRS:
        base = os.path.join(STEP_CHECK_DIR, d)
        rep = json.load(open(os.path.join(base, "report.json")))
        batch_calls = [json.loads(line) for line in open(os.path.join(base, "calls.jsonl"))]
        for c in rep["candidates"]:
            if c["answered"] or c["name"] not in reports:
                reports[c["name"]] = dict(c, batch=d, coverage=rep["coverage"])
                calls[c["name"]] = [r for r in batch_calls if r["candidate"] == c["name"] and r["attempt"] == 0]
    return reports, calls, json.load(open(os.path.join(STEP_CHECK_DIR, "out", "report.json")))


def main():
    runs, total_rows, telecom = load_runs()
    by_case = {}
    for r in runs:  # a later collection of the same case replaces the earlier one
        prev = by_case.get(r["session_id"])
        if prev is None or r["collected_at"] >= prev["collected_at"]:
            by_case[r["session_id"]] = r
    duplicates = len(runs) - len(by_case)
    runs = list(by_case.values())
    for r in runs:
        r["_turns"] = turns(r)
        r["_model"] = run_model(r)
        r["_type"] = issue_type(r)
        r["_fail"] = failure_category(r, r["_turns"])
        r["_transfer"] = any(n == TRANSFER for k, n, _ in r["_turns"] if k == "call")
        r["_no_access"] = any(NO_DEVICE_ACCESS.search(x) for k, _, x in r["_turns"] if k == "say")
    models = sorted({r["_model"] for r in runs})
    by_model = {m: [r for r in runs if r["_model"] == m] for m in models}

    # ---------- results: recorded full runs ----------
    rows = []
    for m in models:
        g = by_model[m]
        n, k = len(g), sum(bool(r["success"]) for r in g)
        cost = sum(Decimal(str(r["agent_cost"])) for r in g)
        rows.append({
            "model": m, "n": n, "correct": k, "accuracy": q4(k / n), "ci95": wilson(k, n),
            "cost_per_correct_cents": q4(cost / k * 100) if k else None,
            "total_agent_cost_usd": float(cost.quantize(Decimal("0.000001"))),
            "mean_tokens_per_case": q4(sum(r["total_tokens"] for r in g) / n),
            "mean_calls_per_case": q4(sum(len(r["spans"]) for r in g) / n),
            "mean_steps_per_case": q4(sum(r["steps"] for r in g) / n),
            "statuses": dict(sorted(Counter(f"{r['status']} (success={str(bool(r['success'])).lower()})" for r in g).items())),
            "failures": dict(sorted(Counter(r["_fail"] for r in g if r["_fail"]).items())),
            "transfers_in_solved_runs": sum(r["_transfer"] for r in g if r["success"]),
            "paired_vs": None,
            "paired_vs_note": "Not computed: the public dataset carries no task identifier, and the simulated user words each opening differently, so runs cannot be matched to the same task across models.",
        })

    # ---------- per type ----------
    per_type = {"recorded_full_runs": {}}
    for m in models:
        per_type["recorded_full_runs"][m] = {}
        for t in sorted({r["_type"] for r in runs}):
            g = [r for r in by_model[m] if r["_type"] == t]
            k = sum(bool(r["success"]) for r in g)
            per_type["recorded_full_runs"][m][t] = {"n": len(g), "correct": k, "accuracy": q4(k / len(g)) if g else None}
    types = Counter(r["_type"] for r in runs)

    # ---------- failures ----------
    def example(cat):
        return {
            "escalated_to_human_on_unsolved_task": "After walking the user through airplane mode, a SIM reseat, a network-mode change and an APN reset, the agent handed the case to a human while the user's data connection still failed, although the task was solvable.",
            "ended_unsolved_without_escalation": "The agent declared that the on-device and account fixes it could perform were exhausted, or left the user with another question, and the conversation ended with the issue still open.",
            "claimed_no_device_access": "Six steps in, the agent escalated, saying it could not run device diagnostics itself; in this benchmark the user runs the device tools on the agent's instructions.",
        }[cat]
    failures = [
        {"category": "escalated_to_human_on_unsolved_task",
         "definition": "An unsolved run (success=false) in which the agent called the transfer_to_human_agents tool. Detected from tool calls, not text. The policy allows a transfer only when the request cannot be handled within the agent's actions; these tasks were solvable.",
         "counts": {m: sum(r["_fail"] == "escalated_to_human_on_unsolved_task" for r in by_model[m]) for m in models},
         "example": example("escalated_to_human_on_unsolved_task")},
        {"category": "ended_unsolved_without_escalation",
         "definition": "An unsolved run (success=false) with no transfer_to_human_agents call. Detected from tool calls, not text.",
         "counts": {m: sum(r["_fail"] == "ended_unsolved_without_escalation" for r in by_model[m]) for m in models},
         "example": example("ended_unsolved_without_escalation")},
        {"category": "claimed_no_device_access",
         "definition": "Any run in which an agent message says it does not have access to the device or device tools (regular-expression text matching on the agent's messages; a sub-pattern, also counted in one of the two categories above when the run was unsolved).",
         "counts": {m: sum(r["_no_access"] for r in by_model[m]) for m in models},
         "counts_unsolved": {m: sum(r["_no_access"] and not r["success"] for r in by_model[m]) for m in models},
         "example": example("claimed_no_device_access")},
    ]

    # ---------- step check ----------
    reports, calls, batch1 = step_check()
    ref_name = next(n for n, c in reports.items() if c["reference"])

    def episodes(rows_, kind):
        out = []
        for r in rows_:
            if r["not_run"] or r["agreement"] is None:
                continue
            if kind == "tool_choice":
                if not r.get("recorded_tools", r.get("recorded")):
                    continue
                out.append({"scenario": r["run"], "node": r["node"], "v": int(r["agreement"] in SAME_TOOL)})
            else:
                out.append({"scenario": r["run"], "node": r["node"], "v": int(r["agreement"] in EXACT)})
        return out

    def paired(cand, kind):
        a, b = episodes(calls[cand], kind), episodes(calls[ref_name], kind)
        shared = {e["node"] for e in a} & {e["node"] for e in b}
        a = [e for e in a if e["node"] in shared]
        b = [e for e in b if e["node"] in shared]
        res = paired_delta(a, b, key="v", n_boot=10000, seed=0)
        return {"reference": ref_name, "n": res["n"], "n_calls": len(shared),
                "delta_points": q4(res["delta"] * 100) if res["delta"] is not None else None,
                "ci95_points": [q4(res["lo"] * 100), q4(res["hi"] * 100)] if res["delta"] is not None else None,
                "unit": "runs (cluster bootstrap over recorded runs; calls averaged within each run first)"}

    step_rows, recompute_mismatch = [], []
    for name, c in reports.items():
        ans = [r for r in calls[name] if not r["not_run"] and r["agreement"] is not None]
        tool_n = [r for r in ans if r.get("recorded_tools", r.get("recorded"))]
        mine_tool = sum(r["agreement"] in SAME_TOOL for r in tool_n)
        mine_exact = sum(r["agreement"] in EXACT for r in ans)
        # The analyzer rounds its rates itself; only differences beyond 4th-decimal rounding count as mismatches.
        if c["tool_choice_rate"] is not None and tool_n and abs(mine_tool / len(tool_n) - c["tool_choice_rate"]) > 0.0001:
            recompute_mismatch.append({"candidate": name, "metric": "tool_choice_rate", "report": c["tool_choice_rate"],
                                       "recomputed": q4(mine_tool / len(tool_n)), "n_report": c["tool_choice_calls"], "n_recomputed": len(tool_n)})
        if c["agreement_rate"] is not None and ans and abs(mine_exact / len(ans) - c["agreement_rate"]) > 0.0001:
            recompute_mismatch.append({"candidate": name, "metric": "agreement_rate", "report": c["agreement_rate"],
                                       "recomputed": q4(mine_exact / len(ans)), "n_report": c["answered"], "n_recomputed": len(ans)})
        step_rows.append({
            "candidate": name, "model": c["model"], "reference": c["reference"], "batch": c["batch"],
            "calls_sent": c["calls_sent"], "answered": c["answered"], "failures": c["failures"],
            "tool_choice": {"n": c["tool_choice_calls"], "matched": mine_tool if c["tool_choice_rate"] is not None else None,
                            "rate": c["tool_choice_rate"], "ci95": c["tool_choice_interval"]},
            "exact_agreement": {"n": c["answered"], "matched": mine_exact if c["agreement_rate"] is not None else None,
                                "rate": c["agreement_rate"], "ci95": c["agreement_interval"]},
            "agreement_breakdown": c["agreement"],
            "cost_per_call_cents": q4(Decimal(c["cost"]["per_call_usd"]) * 100) if c["cost"]["per_call_usd"] else None,
            "tokens_per_call": c["tokens_per_call"], "latency_seconds": c["latency_seconds"],
            "spent_usd": c["spent_usd"],
            "paired_vs": None if c["reference"] else {"tool_choice": paired(name, "tool_choice"), "exact_agreement": paired(name, "exact")},
        })
    batch1_superseded = [c["name"] for c in batch1["candidates"] if not c["answered"]]
    replays = [{
        "name": "step_check_gpt52_recorded_calls",
        "kind": "Kitaru model-swap step check (kitaru-model-swap 0.1.0, zenml-io/kitaru#1327): each sampled recorded GPT-5.2 call is resent, as recorded, to each candidate; the reply is compared with the recorded reply. No agent is re-run and no task outcome is measured.",
        "recorded_model": "gpt-5.2-2025-12-11",
        "coverage": reports[ref_name]["coverage"],
        "sample": "160 of 1048 replayable recorded calls, chosen by the analyzer's deterministic round-robin over node name and model in recorded order; identical in both batches.",
        "candidates": step_rows,
        "analyzer_best_for": batch1["best_for"],
        "analyzer_best_for_note": "The analyzer's own picks from batch 1; batch 1 had no working GPT-5.6 rows, so GPT-5.6 Sol and Luna were not eligible for these picks.",
        "batch1_superseded_candidates": batch1_superseded,
        "recompute_check": recompute_mismatch or "rates recomputed from calls.jsonl match the analyzer's report.json to within 4th-decimal rounding",
    }]

    # ---------- spend ----------
    costs = json.load(open(COSTS))
    parts = [c for c in costs["runs"]]
    recorded_sum = sum(Decimal(c["spent_usd"]) for c in parts if c["spent_usd"] is not None)
    unknown = [c for c in parts if c["spent_usd"] is None]

    # ---------- model table ----------
    model_rows = []
    for m in models:
        model_rows.append({
            "id": m, "id_note": "The dataset's canonical model name; its build script strips routing prefixes (for example openai/Azure/), so the exact string the Exgentic harness sent is not in the data.",
            "role": "recorded full runs" + (" and step-check reference" if m == "gpt-5.2-2025-12-11" else ""),
            "display_name": DISPLAY[m], "vendor": VENDOR[m], "weights": "open" if m in OPEN else "closed",
            "inference_provider_type": None,
            "inference_provider_type_note": "Recorded by Exgentic; spans name the provider as " + ", ".join(sorted({s["attributes"].get("gen_ai.provider.name") or "none" for r in by_model[m] for s in r["spans"]})) + " and the run configs as " + ", ".join(sorted({r["config_path"].split("/")[-2] for r in by_model[m]})) + ".",
            "price_per_mtok_input_usd": None, "price_per_mtok_cached_input_usd": None, "price_per_mtok_output_usd": None,
            "price_date": None,
            "price_note": "The dataset records each run's agent_cost (USD) but not the prices behind it; cost per correct uses agent_cost as recorded.",
        })
    for c in step_rows:
        rep = reports[c["candidate"]]
        if any(x["id"] == c["model"] for x in model_rows):
            x = next(x for x in model_rows if x["id"] == c["model"])
            x["step_check_price"] = rep["price"]
            continue
        disp, vendor, weights = CANDIDATE_INFO[c["model"]]
        host = rep["endpoint_host"]
        openai = host == "api.openai.com"
        price = rep["price"]
        row = {
            "id": c["model"], "role": "step-check candidate", "display_name": disp, "vendor": vendor, "weights": weights,
            "inference_provider_type": "vendor API" if openai else "commercial provider",
            "price_per_mtok_input_usd": float(price["input_per_mtok"]),
            "price_per_mtok_cached_input_usd": float(price["cached_input_per_mtok"]) if price.get("cached_input_per_mtok") else None,
            "price_per_mtok_output_usd": float(price["output_per_mtok"]),
            "price_date": "2026-10-22" if openai else "2026-10-19",
            "price_note": ("genai-prices 0.1.13 table bundled with the analyzer, used on the run date 2026-10-22 (no other date recorded)." if openai
                           else "From benchmarks/haiku-tax/harness/models.py (checked 2026-10-19), which marks these prices UNVERIFIED (third-party listings); cached input billed at the input price."),
        }
        if not openai:
            row["provider_private"] = "provider-a"  # neutral label; the published copy names no provider
        model_rows.append(row)

    best = max(rows, key=lambda r: r["accuracy"])
    worst = min(rows, key=lambda r: r["accuracy"])
    ref_row = next(r for r in step_rows if r["reference"])
    below = [r["candidate"] for r in step_rows if not r["reference"] and r["paired_vs"]["tool_choice"]["ci95_points"][1] < 0]
    esc = failures[0]
    total_unsolved = sum(r["n"] - r["correct"] for r in rows)
    total_esc = sum(esc["counts"].values())
    doc = {
        "meta": {
            "name": "Frontier agents on public tau2-bench Telecom traces",
            "slug": SLUG,
            "question": "On public recorded tau2-bench Telecom runs, how often do five frontier models solve the task, how do they fail, and how far do newer models' answers at each recorded step drift from GPT-5.2's?",
            "domain": "Telecom technical support (customer-service agent with a simulated user who runs the device actions)",
            "status": "complete",
            "run_dates": {
                "recordings": f"{min(s['start_time'][:10] for r in runs for s in r['spans'])} to {max(s['start_time'][:10] for r in runs for s in r['spans'])} (span start times; collected {min(r['collected_at'][:10] for r in runs)} to {max(r['collected_at'][:10] for r in runs)}), by Exgentic",
                "step_check": "2026-10-22",
                "analysis": "2026-10-22",
            },
            "who_ran": "Hamza Tahir (ZenML), with Claude Code agents",
            "kitaru_version": "0.27.2+dev",
            "kitaru_details": {"plugin": "kitaru-model-swap 0.1.0 (plugins/packages/model-swap), built from zenml-io/kitaru branch feature/model-swap-analyzer at 0217140c9bd6fc1b0569abefbaea30be20a6fde4",
                               "importer": "a private script importer mapping each Exgentic run to one Kitaru session and each OTel chat span to one llm_call node (not in this repository)",
                               "note": "The analyzer ran in-process (step_check/swap_run.py) against sessions on a local Kitaru server, so its full result could be written to disk."},
            "harness_git_commit": git_commit(BENCH),
            "harness_git_commit_note": None if git_commit(BENCH) else f"{BENCH} is not committed yet, so git log -1 -- {BENCH} returns nothing.",
            "code_location": BENCH,
            "total_spend_usd": None,
            "total_spend_usd_note": f"{BENCH}/costs.json has {len(parts)} runs: " + "; ".join(f"{c['what']}: {c['spent_usd'] if c['spent_usd'] is not None else 'not recorded'}" for c in parts) + f". Recorded parts sum to {recorded_sum} USD; the unrecorded run is why the total is null. Using the public recordings cost nothing.",
        },
        "dataset": {
            "source": "Exgentic agent-llm-traces-v2 (Hugging Face), tool_calling harness on tau2-bench Telecom",
            "url": "https://huggingface.co/datasets/Exgentic/agent-llm-traces-v2",
            "license": None,
            "license_note": "The dataset card and repository metadata declare no license (checked 2026-10-22).",
            "total_cases": sum(telecom.values()),
            "total_cases_note": f"tau2_telecom rows across all harnesses in the 9 shards ({dict(sorted(telecom.items()))}); the shards hold {total_rows} rows in all.",
            "kept_cases": len(runs),
            "dropped_reason": f"Kept the {HARNESS} harness only (one agent design, native tool calls). No rows were dropped within it; {duplicates} duplicate session_id rows were found.",
            "split": None,
            "split_note": "No split: nothing was tuned on these runs.",
            "types": [{"type": t, "count": types[t]} for t in sorted(types)],
            "types_note": "Issue type is not a dataset field. It is assigned by regular-expression text matching on the simulated user's first three messages, rules in order (first match wins): " + "; ".join(f"{n}: /{p}/" for n, p in TYPE_RULES) + ".",
        },
        "models": model_rows,
        "setup": {
            "conditions": [
                {"name": "recorded_full_runs", "description": "Exgentic's runs of tau2-bench Telecom with its tool_calling agent harness: one run per task per model, the model under test talking to a simulated user who performs the device actions. Outcomes are the dataset's success/score columns; nothing was re-run."},
                {"name": "step_check_gpt52_recorded_calls", "description": "Kitaru's model-swap step check: 160 sampled recorded GPT-5.2 calls resent, as recorded (full conversation up to that step, the recorded tool list), to GPT-5.2 itself (noise floor) and 7 newer candidates; replies compared with GPT-5.2's recorded reply."},
            ],
            "prompt_rewriting": None,
            "prompt_rewriting_note": "No prompt was changed. The agent's policy reaches the model as the first user message in the recordings, and the step check resends it unchanged.",
            "tools": {"agent_tools": sorted({t["name"] for r in runs[:1] for s in r["spans"][:1] for t in json.loads(s["attributes"]["gen_ai.tool.definitions"] or "[]")}),
                      "note": "Every recorded tool definition has an empty parameter schema ({\"type\": \"object\", \"properties\": {}}); the step check passes them as recorded. Device tools (toggles, reboot, APN reset and others) belong to the simulated user, not the agent."},
            "user_simulator": "tau2-bench's LLM user simulator, as run by Exgentic. Its calls were filtered out of this dataset, so its model and cost are not known here.",
            "limits": {"recorded_full_runs": None,
                       "recorded_full_runs_note": "Step and token limits of the Exgentic harness are not recorded in the dataset.",
                       "step_check": {"max_tokens": 4096, "timeout_seconds": 180, "max_retries": 3, "concurrency": 16,
                                      "max_calls": 160, "max_spend_usd": {"batch 1": "20", "batch 2": "8"},
                                      "api": {"gpt-5.6-sol and gpt-5.6-luna (batch 2)": "OpenAI Responses API", "others": "/chat/completions"}}},
        },
        "grading": {
            "judges": [{"name": "tau2-bench task evaluation, as recorded by Exgentic", "applies_to": "recorded_full_runs", "note": "Read from the dataset's success column; not re-graded here."},
                       {"name": "kitaru-model-swap compare (exact, no LLM judge)", "applies_to": "step_check_gpt52_recorded_calls"}],
            "tie_break": None,
            "tie_break_note": "No ranking ties were broken; the step check's analyzer 'Best for' rule (within 10 points of the reference's self-agreement) is reported as the analyzer gave it.",
            "human_agreement": None,
            "human_agreement_note": "No human review: outcomes come from the benchmark's evaluator, and the step check uses exact comparison.",
            "self_grading_check": None,
            "self_grading_check_note": "No LLM judge was used, so no model graded its own output.",
            "metrics": [
                {"name": "accuracy", "definition": "correct / n, where correct = runs with success=true. Every run counts in n."},
                {"name": "cost_per_correct_cents", "definition": "100 x (sum of the dataset's agent_cost over all n runs of the model, solved or not) / correct. agent_cost is Exgentic's figure for the agent-under-test model's calls; how it priced cached tokens is not documented in the dataset. benchmark_cost (the user simulator and evaluation) is excluded."},
                {"name": "mean_tokens_per_case", "definition": "Mean of the dataset's total_tokens per run."},
                {"name": "mean_calls_per_case", "definition": "Mean number of agent chat spans (model calls) per run."},
                {"name": "tool_choice_rate", "definition": "Step check: among answered calls where the recorded GPT-5.2 reply called a tool, the share where the candidate called the same tool (arguments may differ). Kitaru analyzer field tool_choice_rate; Wilson 95% interval."},
                {"name": "exact_agreement_rate", "definition": "Step check: among answered calls, the share with the same tool and same normalized arguments, or the same normalized text. Kitaru analyzer field agreement_rate; Wilson 95% interval."},
                {"name": "step_cost_per_call_cents", "definition": "Step check: mean cost per answered call from the candidate's reported token usage at the price in models[] (cached input at the cached price where one is set)."},
            ],
        },
        "noise": {
            "method": "Recorded outcomes: one run per task per model, no repeats, so no outcome noise floor. Step check: GPT-5.2 resent its own 160 recorded calls once (the reference); its agreement with its own recording is the step-level noise floor.",
            "size": {"tool_choice_self_agreement": ref_row["tool_choice"], "exact_self_agreement": ref_row["exact_agreement"]},
            "ci_method": "Wilson score 95% interval for rates; paired candidate-minus-reference differences use a cluster bootstrap over recorded runs (swapbench.stats.paired_delta, 10000 resamples, seed 0).",
            "resamples": 10000,
            "tie_threshold": None,
            "tie_threshold_note": "No fixed tie threshold for outcomes; differences whose 95% interval includes 0 are reported as not distinguishable.",
        },
        "results": {"recorded_full_runs": rows},
        "results_note": f"One row per recorded run; {duplicates} duplicate cases. Scoring: success=true counts as correct; status 'unsuccessful' and status 'unknown' with success=false count as wrong; status 'unknown' with success=true counts as correct (the dataset's status and success columns disagree on those rows). No runs were dropped: these are third-party recordings, not our harness. Two GPT-5.2 rows carry a Claude or Gemini config_path; they are counted under the model their spans name.",
        "per_type": per_type,
        "per_type_note": "Types come from text matching (see dataset.types_note); counts are small, so read per-type rates with caution.",
        "failures": failures,
        "failures_note": f"{total_esc} of {total_unsolved} unsolved runs ended in an escalation to a human. Categories come from tool calls, except claimed_no_device_access, which is text matching.",
        "replays_and_step_checks": replays,
        "headline_findings": [
            {"finding": f"On {sum(r['n'] for r in rows)} public tau2-bench Telecom runs, {DISPLAY[best['model']]} solved the most tasks and {DISPLAY[worst['model']]} the fewest.",
             "numbers": [f"results.recorded_full_runs[model={best['model']}].accuracy", f"results.recorded_full_runs[model={best['model']}].ci95",
                         f"results.recorded_full_runs[model={worst['model']}].accuracy", f"results.recorded_full_runs[model={worst['model']}].ci95"]},
            {"finding": "Most unsolved runs end with the agent handing the user to a human on a task it could have solved.",
             "numbers": ["failures[category=escalated_to_human_on_unsolved_task].counts"] + [f"results.recorded_full_runs[model={m}].correct" for m in models]},
            {"finding": "Re-sent its own recorded calls, GPT-5.2 picks the same tool only part of the time, which sets the bar any replacement has to be read against.",
             "numbers": ["replays_and_step_checks[name=step_check_gpt52_recorded_calls].candidates[candidate=" + ref_name + "].tool_choice.rate",
                         "replays_and_step_checks[name=step_check_gpt52_recorded_calls].candidates[candidate=" + ref_name + "].tool_choice.ci95"]},
            {"finding": "Of the seven newer candidates, only " + ", ".join(below) + " picked GPT-5.2's recorded tool clearly less often than GPT-5.2's own repeat; every other candidate's paired interval includes zero.",
             "numbers": [f"replays_and_step_checks[name=step_check_gpt52_recorded_calls].candidates[candidate={r['candidate']}].paired_vs.tool_choice.ci95_points" for r in step_rows if not r["reference"]]},
            {"finding": "Unsolved runs cost more per task than solved ones for every model, so failures are also the expensive runs.",
             "numbers": [f"additional_measurements.cost_solved_vs_unsolved[model={m}].{k}" for m in models for k in ("mean_agent_cost_usd_solved", "mean_agent_cost_usd_unsolved")]},
        ],
        "additional_measurements": {
            "cost_solved_vs_unsolved": [{
                "model": m,
                "n_solved": sum(bool(r["success"]) for r in by_model[m]),
                "n_unsolved": sum(not r["success"] for r in by_model[m]),
                "mean_agent_cost_usd_solved": q4(sum(r["agent_cost"] for r in by_model[m] if r["success"]) / max(1, sum(bool(r["success"]) for r in by_model[m]))),
                "mean_agent_cost_usd_unsolved": q4(sum(r["agent_cost"] for r in by_model[m] if not r["success"]) / max(1, sum(not r["success"] for r in by_model[m]))),
                "mean_steps_solved": q4(sum(r["steps"] for r in by_model[m] if r["success"]) / max(1, sum(bool(r["success"]) for r in by_model[m]))),
                "mean_steps_unsolved": q4(sum(r["steps"] for r in by_model[m] if not r["success"]) / max(1, sum(not r["success"] for r in by_model[m]))),
            } for m in models],
        },
        "limitations": [
            "Recorded outcomes are one run per task per model, with no repeats, so no outcome noise floor was measured.",
            "Runs cannot be paired by task across models (no task identifier in the public data), so model-vs-model differences are unpaired and only their separate Wilson intervals are reported.",
            "The step check measures similarity to GPT-5.2's recorded replies, not correctness; no candidate's task success was measured, so it cannot say which model would solve more tasks.",
            "Only one recorded model (GPT-5.2) could be reached for the step check; Claude Opus 4.5, Gemini 3 Pro, DeepSeek V3.2 and Kimi K2.5 as recorded were not reachable with the available keys, so step agreement could not be compared with recorded outcomes.",
            "Recorded tool definitions have empty parameter schemas, so candidates saw tool names and descriptions but no argument schemas; this affects every candidate including the reference.",
            "OpenAI rejected 19 of the 160 calls for every OpenAI candidate (a recorded tool-call id longer than OpenAI's 64-character limit); those calls are excluded from the OpenAI candidates' rates, so OpenAI and non-OpenAI candidates are scored on slightly different call sets.",
            "9 of 1057 recorded GPT-5.2 calls were skipped by the analyzer for a missing tool schema.",
            "The recorded GPT-5.2 settings (reasoning effort, temperature) are not in the data; the step check used provider defaults.",
            "Issue types and the claimed_no_device_access category come from text matching, not human labels.",
            "agent_cost is Exgentic's figure; its prices and cached-token treatment are undocumented, and the user simulator's cost is excluded.",
            "Open-weight candidate prices in the step check are unverified third-party listings.",
            "One step-check run's spend was not recorded (its result exceeded Kitaru's 1 MB worker task-result limit and was discarded), so total spend is null.",
            "The dataset declares no license.",
        ],
        "public_safety": [
            {"item": "Inference provider of the open-weight step-check candidates", "why": "Provider names stay private in these exports.", "where_in_file": "models[*].provider_private; replays_and_step_checks[0].candidates[*] (endpoint not included)"},
            {"item": "Open-weight candidate prices", "why": "Unverified third-party listings.", "where_in_file": "models[role=step-check candidate, weights=open].price_*"},
            {"item": "Dataset license", "why": "Exgentic declares no license; quoting trace content publicly needs their permission or a license. The failure examples here are paraphrases.", "where_in_file": "dataset.license, failures[*].example"},
            {"item": "Unreleased Kitaru analyzer and its bugs", "why": "kitaru-model-swap comes from an unmerged PR (zenml-io/kitaru#1327); the 1 MB result limit and the 64-character tool-call id failures are unreleased-software issues.", "where_in_file": "meta.kitaru_details, limitations, meta.total_spend_usd_note"},
        ],
        "inconsistencies": [],
    }

    # ---------- inconsistencies (data vs write-ups) ----------
    incons = doc["inconsistencies"]
    incons.append({"where": "Dataset card (README.md)", "claim": "10,057 agent runs (sessions)", "data": f"{total_rows} rows across the 9 published shards"})
    resp = Counter()
    for r in runs:
        for s in r["spans"]:
            resp[(r["_model"], s["attributes"].get("gen_ai.response.model"))] += 1
    non_canon = {f"{m} -> {v}": n for (m, v), n in resp.items() if v != m}
    incons.append({"where": "Dataset card (README.md)", "claim": "gen_ai.request.model / gen_ai.response.model in spans use the canonical model name, with zero mismatches",
                   "data": f"In the {HARNESS} tau2_telecom slice, spans whose response model differs from the canonical name: {dict(sorted(non_canon.items()))}"})
    mislabeled = [{"session_id": r["session_id"], "model": r["_model"], "config_path": r["config_path"]} for r in runs if r["_model"] not in r["config_path"]]
    incons.append({"where": "Dataset rows", "claim": "config_path names the run's experiment and model", "data": f"{len(mislabeled)} GPT-5.2 rows carry another model's config_path: {mislabeled}"})
    unk = Counter(bool(r["success"]) for r in runs if r["status"] == "unknown")
    incons.append({"where": "Dataset rows", "claim": "status describes the outcome", "data": f"{sum(unk.values())} rows have status 'unknown' while success is set: {unk[True]} true, {unk[False]} false"})
    incons.append({"where": "Kitaru post-import insights card (this session's import of a 125-run sample)", "claim": "6 recorded models appear in these sessions",
                   "data": "5 models; the sixth name is Claude Opus 4.5's Bedrock response model id on 33 of the sample's calls"})
    incons.append({"where": "Kitaru post-import insights card (125-run sample)", "claim": "100% of sessions include explicit correction language",
                   "data": "The agent policy arrives as the first user message and contains the marker words, so every session matches regardless of what the user said"})
    incons.append({"where": "Kitaru model-swap report notes", "claim": "160 sampled calls have no system prompt",
                   "data": "Each call's first user message carries the full agent policy; the recordings have no system role, not no instructions"})
    samp = {"gpt-5.2-2025-12-11": (15, 25)}
    g = by_model["gpt-5.2-2025-12-11"]
    incons.append({"where": "Earlier chat summary in this session (125-run sample, 25 per model)", "claim": f"GPT-5.2 failed 10 of 25 sampled runs (solved {samp['gpt-5.2-2025-12-11'][0]}/{samp['gpt-5.2-2025-12-11'][1]} = 0.6000)",
                   "data": f"On all {len(g)} GPT-5.2 runs: {sum(bool(r['success']) for r in g)} solved (accuracy {q4(sum(bool(r['success']) for r in g) / len(g))})"})
    if recompute_mismatch:
        incons.append({"where": "Kitaru model-swap report.json vs calls.jsonl", "claim": "analyzer rates", "data": recompute_mismatch})

    with open(OUT, "w") as f:
        json.dump(doc, f, indent=1, ensure_ascii=False)
        f.write("\n")
    print("wrote", OUT)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--step-check-dir", default=STEP_CHECK_DIR)
    ap.add_argument("--out", default=OUT)
    a = ap.parse_args()
    STEP_CHECK_DIR, OUT = a.step_check_dir, a.out
    main()
