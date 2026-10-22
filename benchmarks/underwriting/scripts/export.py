"""Build results/underwriting.json (the export, schema in the repo's EXPORT_SCHEMA.md) from this benchmark's committed
result files only.

  python scripts/export.py [OUT]     # default OUT: results/underwriting.json; needs env/tasks.json (scripts/fetch_data.sh)

Ported from the original run's export script; the changes are the neutral provider label (@provider-a), paths relative
to this directory, a fixed original commit instead of a git lookup, and the added `inconsistencies` section.
No model calls. Numbers already published (paired deltas, Wilson intervals) are read from the stored summaries so the
export matches the report; everything else is recomputed from the per-case rows.
"""
import json
import math
import os
import re
import sys
from collections import Counter, defaultdict

UW = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(UW, "results", "underwriting.json")
ORIGINAL_COMMIT = "84411cff33aa4085450ffcf28c2276f3f34efc84"  # last commit touching the benchmark in the private repo

MODELS = {  # key: (exact model id, display, vendor, weights)
    "opus-5.5": ("claude-opus-5-5", "Claude Opus 5.5", "Anthropic", "closed"),
    "sonnet-5.5": ("claude-sonnet-5-5", "Claude Sonnet 5.5", "Anthropic", "closed"),
    "haiku-5.5": ("claude-haiku-5-5", "Claude Haiku 5.5", "Anthropic", "closed"),
    "gpt-6.1-sol": ("gpt-6.1-sol", "GPT-6.1 Sol", "OpenAI", "closed"),
    "gpt-6-luna": ("gpt-6-luna", "GPT-6 Luna", "OpenAI", "closed"),
    "deepseek-v4-pro@provider-a": ("deepseek-ai/DeepSeek-V4-Pro-0813", "DeepSeek V4 Pro", "DeepSeek", "open"),
    "deepseek-v4.1-flash@provider-a": ("deepseek-ai/DeepSeek-V4.1-Flash", "DeepSeek V4.1 Flash", "DeepSeek", "open"),
    "glm-5.3@provider-a": ("zai-org/GLM-5.3", "GLM 5.3", "Z.ai", "open"),
    "glm-5.3-flash@provider-a": ("zai-org/GLM-5.3-Flash", "GLM 5.3 Flash", "Z.ai", "open"),
    "gpt-oss-120b@provider-a": ("openai/gpt-oss-120b", "gpt-oss-120b", "OpenAI", "open"),
    "qwen3.8-27b@provider-a": ("Qwen/Qwen3.8-27B", "Qwen3.8 27B", "Alibaba (Qwen)", "open"),
    "minimax-m3@provider-a": ("MiniMaxAI/MiniMax-M3", "MiniMax-M3", "MiniMax", "open"),
}
PRICES = {  # USD per 1M tokens (input, cached input, output) from src/models_client/models.py
    "opus-5.5": (4.00, 0.20, 20.00), "sonnet-5.5": (2.00, 0.10, 10.00), "haiku-5.5": (0.10, 0.01, 0.50),
    "gpt-6.1-sol": (2.00, 0.10, 10.00), "gpt-6-luna": (0.10, 0.01, 0.50),
    "deepseek-v4-pro@provider-a": (1.75, 0.15, 3.50), "deepseek-v4.1-flash@provider-a": (0.30, 0.30, 1.20),
    "glm-5.3@provider-a": (1.40, 1.40, 4.40), "glm-5.3-flash@provider-a": (0.15, 0.15, 0.50),
    "gpt-oss-120b@provider-a": (0.15, 0.15, 0.60), "qwen3.8-27b@provider-a": (0.45, 0.45, 3.00),
    "minimax-m3@provider-a": (0.30, 0.30, 1.20),
}
INCONSISTENCIES = [  # found while porting (2026-10-22) by regenerating every table from the committed rows
    {"item": "GPT-6 Luna, first prompt, 252 cases",
     "published": "218/252 (86.5%), api_error 1, -10.7 pts [-15.1, -6.7] vs Opus 5.5 (original write-up, "
                  "results/tables.md, results/summary.json, results/report.html)",
     "from_rows": "219/252 (0.8690), no api_error; -10.3 pts [-14.7, -6.3] vs Opus 5.5 when report.py is run in the "
                  "original file order",
     "why": "Two of Luna's cases hit provider API errors and were re-run; results/summary.json was written in the same "
            "minute as the re-run, after one of the two re-runs had finished and before the other. The rows are "
            "complete; the published table is one case stale.",
     "where_in_file": "results.first_prompt_all_cases[model=gpt-6-luna]: accuracy and counts come from the rows "
                      "(219), but paired_vs was copied from the stale summary (-10.7 [-15.1, -6.7]); "
                      "grading.self_grading_check.note has the direction reversed (219 is the final count)."},
    {"item": "Bootstrap intervals in harness/report.py depend on file order",
     "published": "Intervals in results/tables.md",
     "from_rows": "Identical only when the run files are read in the original run's order; in another order the "
                  "intervals move by up to 0.4 points (point estimates never change)",
     "why": "report.py draws every model's bootstrap from one random stream in the order glob() lists results/runs/, "
            "which depends on the filesystem. scripts/check_tables.py replays the original order.",
     "where_in_file": "results.first_prompt_all_cases[*].paired_vs.ci95_points"},
    {"item": "Tuned-section intervals in the original write-up",
     "published": "Sonnet 5.5 tuned +10.1 [+5.4, +15.5]; Haiku 5.5 tuned +12.0 [+6.6, +18.0]; gpt-oss-120b tuned "
                  "+20.2 [+10.1, +29.8]; Sonnet 5.5 effort medium -7.7 [-15.5, -0.6]; Opus 5.5 effort low -3.6 "
                  "[-7.7, 0.0]",
     "from_rows": "[+5.4, +14.9]; [+6.6, +17.4]; [+10.7, +29.8]; [-14.9, -0.6]; [-7.1, 0.0] (this file and "
                  "results/tuned/summary.json)",
     "why": "tuned_report.py shares one random stream across arms; adding the shared-prompt arms the next day "
            "shifted the stream. Point estimates and conclusions are unchanged.",
     "where_in_file": "results.per_model_rewritten_prompt_held_out, results.effort_*_held_out"},
    {"item": "Why 128 of 380 cases were dropped",
     "published": "dataset.dropped_reason: 'the 128 cases where [the oracle] disagrees with the published reference'",
     "from_rows": "Rebuilding the environment (env/oracle.py) drops 128 for four reasons: the rebuilt environment "
                  "cannot resolve the case 53, the company's NAICS code is not recoverable 44, the reference uses "
                  "a later environment version ('qualified') 25, the oracle disagrees 6",
     "why": "The dropped_reason sentence simplified the oracle's report.",
     "where_in_file": "dataset.dropped_reason"},
    {"item": "Step-level screen: 'picks'",
     "published": "replay/comparison.json picks (from the analyzer version used on 2026-10-21)",
     "from_rows": "Re-running replay/analyze.py --grade on the private analyzer outputs reproduces every row, "
                  "correlation and finalist exactly, but the analyzer's own 'Best for' picks differ at Kitaru commit "
                  "0217140, whose report logic changed after the run",
     "why": "The picks come from the Kitaru plugin's report code, not from this benchmark.",
     "where_in_file": "replays_and_step_checks[0] (picks are not exported; rows and finalists are)"},
]

TYPE_NAMES = {"Small Business Elibility Check": "Small business eligibility"}
ASKS = re.compile(r"\?|\b(i need|please (provide|share|confirm)|could you|can you|need (the|these|following))\b", re.I)


def bare(key):
    return key.split("@")[0]


def load(path):
    rows = {}
    for line in open(path):
        r = json.loads(line)
        rows[r["task"]] = r  # a re-run of a task replaces the earlier row
    return rows


def wilson(k, n, z=1.96):
    if not n:
        return None
    p = k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return [round((c - h) / d, 4), round((c + h) / d, 4)]


def classify(r):
    """Failure category of a wrong case: the harness status, else a text pattern on the final answer."""
    if r["success"]:
        return None
    if r["status"] != "finished":
        return r["status"]
    fa = (r.get("final_answer") or "").strip()
    body = re.sub(r"^\W*FINAL ANSWER:?\W*", "", fa, flags=re.I).strip()
    if len(body) < 15:
        return "empty_final_answer"
    if ASKS.search(body[:400]):
        return "final_answer_asks_for_information"
    return "wrong_decision"


def stats(rows):
    rows = [r for r in rows.values() if r["status"] != "harness_error"]
    n, k = len(rows), sum(bool(r["success"]) for r in rows)
    cost = sum(r["cost"] for r in rows)
    tok = [r["input"] + r["output"] for r in rows]
    harness_flags = Counter(f for r in rows for f in r["failures"])
    cats = Counter(c for c in map(classify, rows) if c)
    return dict(
        n=n, correct=k, accuracy=round(k / n, 4) if n else None, ci95_wilson=wilson(k, n),
        cost_per_case_cents=round(cost / n * 100, 4) if n else None,
        cost_per_correct_cents=round(cost / k * 100, 4) if k else None,
        mean_tokens_per_case=round(sum(tok) / n, 1) if n else None,
        mean_input_tokens_per_case=round(sum(r["input"] for r in rows) / n, 1) if n else None,
        mean_cached_input_tokens_per_case=round(sum(r["cached"] for r in rows) / n, 1) if n else None,
        mean_output_tokens_per_case=round(sum(r["output"] for r in rows) / n, 1) if n else None,
        mean_calls_per_case=round(sum(r["calls"] for r in rows) / n, 2) if n else None,
        mean_tool_calls_per_case=round(sum(r["tool_calls"] or 0 for r in rows) / n, 2) if n else None,
        statuses=dict(Counter(r["status"] for r in rows)),
        cases_with_harness_flag=dict(harness_flags),
        wrong_by_category=dict(cats),
    )


def by_type(rows):
    out = defaultdict(lambda: dict(n=0, correct=0))
    for r in rows.values():
        if r["status"] == "harness_error":
            continue
        t = TYPE_NAMES.get(r["task_type"], r["task_type"])
        out[t]["n"] += 1
        out[t]["correct"] += bool(r["success"])
    return {t: v | {"accuracy": round(v["correct"] / v["n"], 4)} for t, v in sorted(out.items())}


def pct(d):
    return {k: (round(v, 4) if isinstance(v, float) else v) for k, v in d.items()} if d else None


def main():
    tasks = {t["id"]: t for t in json.load(open(os.path.join(UW, "env", "tasks.json")))}
    split = json.load(open(os.path.join(UW, "env", "split.json")))
    held = set(split["held"])
    base = {k: load(os.path.join(UW, "results", "runs", f"{k}.jsonl")) for k in MODELS}
    summary = json.load(open(os.path.join(UW, "results", "summary.json")))["models"]
    tuned_sum = json.load(open(os.path.join(UW, "results", "tuned", "summary.json")))
    arms = defaultdict(dict)
    for k in MODELS:
        for arm in ("tuned", "shared", "effort-high", "effort-medium", "effort-low", "repeat"):
            p = os.path.join(UW, "results", "tuned", "runs", f"{k}__{arm}.jsonl")
            if os.path.exists(p):
                arms[arm][k] = {t: r for t, r in load(p).items() if t in held}
    arms["shared"]["sonnet-5.5"] = arms["tuned"]["sonnet-5.5"]  # the shared prompt is Sonnet's own tuned prompt

    def row(k, rows, vs=None):
        return {"model": bare(k), **stats(rows), **({"paired_vs": vs} if vs else {})}

    results, per_type = {}, {}
    results["first_prompt_all_cases"] = []
    per_type["first_prompt_all_cases"] = {}
    for k in sorted(MODELS, key=lambda m: -summary[m]["accuracy"]):
        v = summary[k].get("vs_ref") or {}
        vs = {"reference": "opus-5.5", "n": v.get("n"), "delta_points": round(v["delta"] * 100, 1),
              "ci95_points": [round(v["lo"] * 100, 1), round(v["hi"] * 100, 1)]} if v.get("delta") is not None else None
        results["first_prompt_all_cases"].append(row(k, base[k], vs))
        per_type["first_prompt_all_cases"][bare(k)] = by_type(base[k])

    def held_rows(k):
        return {t: r for t, r in base[k].items() if t in held}

    conds = [("first_prompt_held_out", None), ("shared_rewritten_prompt_held_out", "shared"),
             ("per_model_rewritten_prompt_held_out", "tuned"), ("effort_high_held_out", "effort-high"),
             ("effort_medium_held_out", "effort-medium"), ("effort_low_held_out", "effort-low"),
             ("repeat_unchanged_held_out", "repeat")]
    for name, arm in conds:
        results[name], per_type[name] = [], {}
        models = MODELS if arm is None else arms[arm]
        for k in models:
            rows = held_rows(k) if arm is None else arms[arm][k]
            vs = None
            if arm:
                a = "tuned" if (arm == "shared" and k == "sonnet-5.5") else arm
                d = tuned_sum["arms"][k][a]["vs_original"]
                vs = {"reference": "same model, first prompt, held-out cases", "n": d["n"],
                      "delta_points": round(d["delta"] * 100, 1),
                      "ci95_points": [round(d["lo"] * 100, 1), round(d["hi"] * 100, 1)]}
            results[name].append(row(k, rows, vs))
            per_type[name][bare(k)] = by_type(rows)
        results[name].sort(key=lambda x: -(x["accuracy"] or 0))

    # Failure categories with counts per model on the first-prompt run (all 252 cases).
    defs = {
        "final_answer_asks_for_information": "Wrong case whose final answer asks the underwriter for information "
        "instead of deciding (the FINAL ANSWER marker was put on a question). Text-pattern classification.",
        "empty_final_answer": "Wrong case whose final answer is empty or a fragment under 15 characters.",
        "wrong_decision": "The agent gave a complete answer that the judges ruled does not match the reference.",
        "step_limit": "Ran out of the 30-model-call budget; scored wrong.",
        "turn_limit": "Used all 12 underwriter turns without a final answer; scored wrong.",
        "empty_reply": "The model returned empty turns after two 'Please continue.' nudges; scored wrong.",
        "api_error": "The provider API kept failing (HTTP 520) after retries; scored wrong.",
        "harness_error": "A network error in our harness (connection reset); the case is dropped from n, not scored.",
    }
    examples = {
        "final_answer_asks_for_information": "FINAL ANSWER: I can help assess appetite, but I need the following "
        "application details: business operations and NAICS code, requested line of business, state, annual revenue.",
        "empty_final_answer": "FINAL ANSWER: (nothing after the marker)",
        "wrong_decision": "Answered that property appetite was 'pending construction verification' where the "
        "guidelines put the business in appetite.",
        "step_limit": "Kept re-querying the NAICS and appetite tables until the 30-call budget ran out.",
        "turn_limit": "Kept asking the underwriter for details already provided until 12 turns were used.",
        "empty_reply": "Returned an empty message three times in a row.",
        "api_error": "Provider returned HTTP 520 on every retry.",
        "harness_error": "Connection reset by peer during the run.",
    }
    failures = []
    for cat, definition in defs.items():
        counts = {}
        for k in MODELS:
            rows = base[k].values()
            counts[bare(k)] = (sum(r["status"] == "harness_error" for r in rows) if cat == "harness_error"
                               else sum(classify(r) == cat for r in rows if r["status"] != "harness_error"))
        failures.append({"category": cat, "definition": definition, "scope": "first_prompt_all_cases",
                         "counts": counts, "example": examples[cat]})
    failures.append({
        "category": "unreadable_tool_call",
        "definition": "Cases with at least one tool call whose arguments were not valid JSON (harness flag "
        "tool_parse_error). The agent got an error message and could continue, so this overlaps the categories above.",
        "scope": "first_prompt_all_cases",
        "counts": {bare(k): sum("tool_parse_error" in r["failures"] for r in base[k].values()) for k in MODELS},
        "example": "A read_query call whose arguments were a truncated JSON string.",
    })

    # Step-level replay through the Kitaru model-swap analyzer, and the Kitaru full replay.
    comp = json.load(open(os.path.join(UW, "replay", "comparison.json")))
    step_rows = []
    for r in comp["rows"]:
        f = r.get("full")
        step_rows.append({
            "model": bare(r["name"]), "is_reference": r["reference"], "recorded_calls_replayed": r["answered"],
            "same_tool_as_reference": r["tool_choice"], "same_tool_and_args": r["exact"],
            "judge_adjusted_agreement": r["judge_adjusted"],
            "same_tool_on_database_query_steps": round(r["query_tool"], 4),
            "final_answer_steps": r["final_steps"], "correct_at_final_answer_steps": round(r["final_correct"], 4),
            "step_cost_per_call_usd": float(r["step_cost_per_call"]),
            "full_run_vs_reference": None if not f else {
                "n": f["n"], "full_run_accuracy": round(f["success"], 4), "delta_points": round(f["delta"] * 100, 1),
                "ci95_points": [round(f["lo"] * 100, 1), round(f["hi"] * 100, 1)],
                "cost_per_correct_cents": round(f["cost_per_success"] * 100, 4)},
        })
    kr = json.load(open(os.path.join(UW, "kitaru_replay", "results.json")))
    full_replays = []
    for k, v in kr.items():
        d = v["vs_baseline"]
        full_replays.append({
            "candidate": bare(k), "n": v["n"], "candidate_correct": v["replay_correct"],
            "reference_correct_same_cases": v["baseline_correct"],
            "delta_points": round(d["delta"] * 100, 1), "ci95_points": [round(d["lo"] * 100, 1), round(d["hi"] * 100, 1)],
            "candidate_cost_per_correct_cents": round(v["replay_cost_per_correct"] * 100, 4),
            "reference_cost_per_correct_cents": round(v["baseline_cost_per_correct"] * 100, 4),
        })
    full_replays.sort(key=lambda x: -x["delta_points"])
    regrade = json.load(open(os.path.join(UW, "results", "regrade_self.json")))["models"]
    jv = json.load(open(os.path.join(UW, "results", "judge_validation.json")))
    probe = json.load(open(os.path.join(UW, "results", "probe.json")))
    hc = {}
    for k in MODELS:
        p = os.path.join(UW, "results", "tuned", "hillclimb", f"{k}.json")
        if os.path.exists(p):
            h = json.load(open(p))
            hc[bare(k)] = {"rounds": [{x: r.get(x) for x in ("round", "learn_correct", "learn_n", "kept", "error")
                                       if r.get(x) is not None} for r in h["rounds"]],
                           "best_round": h.get("best_round"), "optimizer_cost_usd": round(h["optimizer_cost"], 4)}

    def pair_agree(rowsets):
        n = a = 0
        for rows in rowsets:
            for r in rows.values():
                v = [x[1] for x in (r.get("verdicts") or [])[:2]]
                if len(v) == 2 and None not in v:
                    n += 1
                    a += v[0] == v[1]
        return {"n": n, "agreed": a, "rate": round(a / n, 4) if n else None}

    judge_pair_agreement = {
        "description": "How often the two primary judges gave the same verdict (cases where both returned one), "
                       "all models pooled, on the held-out cases.",
        "first_prompt_held_out": pair_agree([held_rows(k) for k in MODELS]),
        "shared_rewritten_prompt_held_out": pair_agree(arms["shared"].values()),
    }
    type_counts = Counter(TYPE_NAMES.get(t["task"], t["task"]) for t in tasks.values())
    split_counts = {s: dict(Counter(TYPE_NAMES.get(tasks[i]["task"], tasks[i]["task"]) for i in split[s]))
                    for s in ("learn", "held")}
    commit = ORIGINAL_COMMIT

    def acc(cond, model):
        return next(r for r in results[cond] if r["model"] == model)

    noise = acc("repeat_unchanged_held_out", "sonnet-5.5")["paired_vs"]
    export = {
        "meta": {
            "name": "Underwriting agent: cost of a correct decision",
            "slug": "underwriting",
            "question": "What does a correct decision cost when 12 models run the same insurance underwriting agent, "
                        "and how much of the gap between models is the prompt?",
            "domain": "Commercial insurance underwriting (small-business applications)",
            "status": "complete",
            "run_dates": {"first_run": "2026-10-21", "tuned_and_effort_runs": "2026-10-21",
                          "shared_prompt_run": "2026-10-22"},
            "who_ran": "Hamza Tahir (ZenML), with Claude Code agents",
            "kitaru_version": "kitaru 0.27.2+dev (branch feature/model-swap-analyzer), kitaru-model-swap plugin 0.1.0; "
                              "used for the step-level replay and the full replay only, not for the main runs",
            "harness_git_commit": commit,
            "code_location": "zenml-io/agent-benchmarks: benchmarks/underwriting (harness/, env/, src/, replay/, kitaru_replay/)",
            "code_location_note": "Ported from a private research repository; harness_git_commit is the last commit there "
                                  "that touched the benchmark.",
            "total_spend_usd": 259.15,
            "total_spend_note": "From the run's spend log (RERUN.md, section 7): every model call (agent, simulated underwriter, "
                                "judges, optimizer) at list prices, plus smoke tests and pilots. Main 12-model run "
                                "$79.49; tuned prompts and effort $85.63; shared prompt $47.38; step-level replays "
                                "$15.85 + $15.62; Kitaru full replay $9.11 (of which about $1.50 estimated).",
        },
        "dataset": {
            "source": "Snorkel AI, Multi-Turn Insurance Underwriting and Multi-Turn Insurance Underwriting Code-Gen",
            "url": ["https://huggingface.co/datasets/snorkelai/Multi-Turn-Insurance-Underwriting",
                    "https://huggingface.co/datasets/snorkelai/Multi-Turn-Insurance-Underwriting-Code-Gen"],
            "license": "Apache-2.0",
            "other_sources": ["US Census Bureau 2022 NAICS codes and concordances (public domain)",
                              "SBA size standards as recovered from the published traces"],
            "total_cases": 380,
            "kept_cases": len(tasks),
            "dropped_reason": "The insurer's environment (database, appetite guide, guidelines) is not published; we "
                              "rebuilt it from the traces. A rule-based oracle (env/oracle.py) re-derives each "
                              "reference answer from the rebuilt environment; the 128 cases where it disagrees with "
                              "the published reference are dropped, so every scored case is answerable from data the "
                              "agent can see.",
            "split": {"method": "stratified by question type, by hash of the case id (env/split.json)",
                      "learning": len(split["learn"]), "held_out": len(split["held"]),
                      "learning_by_type": split_counts["learn"], "held_out_by_type": split_counts["held"],
                      "note": "The first run used all 252 cases. Prompt tuning saw only the learning cases; every "
                              "tuned, shared-prompt, effort and repeat result is on the 168 held-out cases."},
            "types": [{"type": t, "count": c} for t, c in type_counts.most_common()],
        },
        "models": [{
            "id": MODELS[k][0], "harness_key": bare(k), "display_name": MODELS[k][1], "vendor": MODELS[k][2],
            "weights": MODELS[k][3],
            "inference_provider_type": "vendor API" if MODELS[k][3] == "closed" else "commercial provider",
            **({"provider_label": k.split("@")[1]} if "@" in k else {}),
            "price_per_mtok_input_usd": PRICES[k][0], "price_per_mtok_cached_input_usd": PRICES[k][1],
            "price_per_mtok_output_usd": PRICES[k][2],
            "price_date": "2026-10-19",
            "price_note": None if MODELS[k][3] == "closed" else
            "Provider price page needs a login; taken from an earlier pinned table and third-party listings, "
            "unverified. Cached input billed at the full input price.",
        } for k in MODELS],
        "setup": {
            "conditions": [
                {"name": "first_prompt_all_cases", "description": "One system prompt written once, the same for every "
                 "model; default settings; all 252 cases."},
                {"name": "first_prompt_held_out", "description": "The same runs restricted to the 168 held-out cases "
                 "(the baseline for every tuned comparison)."},
                {"name": "per_model_rewritten_prompt_held_out", "description": "Each model's own rewritten prompt "
                 "from up to two rounds of tuning on the 84 learning cases. Run for the 7 models where a rewrite "
                 "improved the learning score."},
                {"name": "shared_rewritten_prompt_held_out", "description": "Sonnet 5.5's rewritten prompt, unchanged, "
                 "on all 12 models. Sonnet's row is its own tuned run."},
                {"name": "effort_high_held_out / effort_medium_held_out / effort_low_held_out", "description":
                 "First prompt with a different reasoning-effort setting (Anthropic output_config.effort, OpenAI "
                 "reasoning.effort); run for Opus, Sonnet, Haiku, GPT-6.1 Sol and GPT-6 Luna."},
                {"name": "repeat_unchanged_held_out", "description": "Sonnet 5.5 run again with nothing changed: the "
                 "noise floor."},
            ],
            "prompt_rewriting": {
                "method": "Claude Opus 5.5 read up to 12 failed learning cases (conversation tail, final answer, "
                          "reference, grader reason) and rewrote the whole system prompt with general instructions. "
                          "A rewrite was kept only if it scored higher on the 84 learning cases; at most 2 rounds.",
                "leakage_check": "A rewrite was rejected and retried if it contained any number of 3+ digits not in "
                                 "the original prompt, or any company name from the learning cases. The held-out "
                                 "cases were never shown to the optimizer.",
                "optimizer_cost_usd_total": round(sum(v["optimizer_cost_usd"] for v in hc.values()), 4),
                "per_model_tuning_log": hc,
                "what_changed": "Conversation discipline, not underwriting knowledge: ask which line of business the "
                                "application is for before recommending others; classify the business from the "
                                "database when no code is given and treat it as settled; commit to one answer; never "
                                "end the case on a question; answer only what was asked.",
            },
            "tools": ["list_tables", "get_table_descriptions", "get_table_schema", "get_table_data_dictionary",
                      "read_query (read-only SQL over the rebuilt insurer database)", "get_underwriting_guidelines"],
            "user_simulator": "Claude Haiku 5.5 plays the underwriter: it holds the company's application details "
                              "from the dataset, opens with the case's request, and answers the agent's questions from "
                              "that data only. It does not know the answer. Its cost is reported apart from the agent's.",
            "limits": "30 agent model calls and 12 underwriter turns per case; the case ends at a message containing "
                      "'FINAL ANSWER:'; an empty agent turn gets 'Please continue.' at most twice; tool results "
                      "capped at 200 rows.",
        },
        "grading": {
            "judges": ["gpt-6-luna", "claude-haiku-5-5"],
            "tie_break": "If the two judges disagree (or one fails to return a verdict), GPT-6.1 Sol decides.",
            "human_agreement": [{"judge": bare(k), "rate": round(v["agreement"], 4), "n": v["n"],
                                 "cohens_kappa": round(v["kappa"], 4), "false_pass": v["false_pass"],
                                 "false_fail": v["false_fail"]} for k, v in jv.items()],
            "human_agreement_note": "Each judge alone against Snorkel's own correctness labels on its published "
                                    "traces (results/judge_validation.json). The two-judge-plus-tiebreak panel was not "
                                    "validated as a unit.",
            "self_grading_check": {
                "description": "Three judges are also candidates. Their first-prompt answers were re-graded by the "
                               "two judges among Luna, Haiku and Sol that are not the model, with Opus 5.5 breaking "
                               "ties (results/regrade_self.json).",
                "results": [{"model": k, "n": v["n"], "correct_original_grading": v["before"],
                             "correct_regraded": v["after"], "cases_changed": len(v["flips"]),
                             "delta_points": round((v["after"] - v["before"]) / v["n"] * 100, 1)}
                            for k, v in regrade.items()],
                "note": "Original-grading counts here include the API-error rows exactly as stored at re-grade time; "
                        "GPT-6 Luna's stored count was 219 then and is 218 in the final table after a re-run.",
            },
            "judge_pair_agreement": judge_pair_agreement,
            "metrics": [
                {"name": "accuracy", "definition": "correct / n, where n counts every scored case including "
                 "step-limit, turn-limit, empty-reply and API-error cases (scored wrong). Harness errors (network "
                 "resets in our code) are dropped from n."},
                {"name": "cost_per_correct_cents", "definition": "100 x sum over the n cases of the agent's model-call "
                 "cost in USD / correct. Agent cost per call = (uncached input tokens x input price + cached input "
                 "tokens x cached price + (output + reasoning) tokens x output price) / 1e6. Excludes the simulated "
                 "underwriter and the judges."},
                {"name": "cost_per_case_cents", "definition": "100 x agent cost in USD / n."},
                {"name": "mean_tokens_per_case", "definition": "mean of (input tokens including cached + output "
                 "tokens) over the agent's calls in a case."},
                {"name": "mean_calls_per_case", "definition": "mean number of agent model calls per case."},
                {"name": "ci95_wilson", "definition": "Wilson score 95% interval on accuracy."},
                {"name": "paired_vs.delta_points", "definition": "accuracy difference in points on the same cases; "
                 "95% interval from a paired bootstrap."},
            ],
        },
        "noise": {
            "method": "Sonnet 5.5 run a second time on the 168 held-out cases with the first prompt and the same "
                      "settings, paired against its first run.",
            "size_points": noise["delta_points"], "size_ci95_points": noise["ci95_points"], "n": noise["n"],
            "ci_method": "Paired bootstrap over cases (resample case-level differences with replacement), percentile "
                         "interval; Wilson score intervals for single accuracies.",
            "resamples": 4000,
            "tie_threshold": "A difference is called a tie when its 95% interval includes 0. In prose we also treat "
                             "differences under 3 points as noise, given the 2.4-point repeat difference.",
        },
        "results_note": "Rows are de-duplicated by case (a re-run replaces the earlier row). Step-limit, turn-limit, "
                        "empty-reply and API-error cases stay in n and count as wrong. Harness errors (5 rows, all in "
                        "held-out arms: Sol effort-low 1, Luna effort-high 2, Haiku tuned 1, GLM 5.3 Flash tuned 1) "
                        "are dropped from n. wrong_by_category splits the wrong cases; cases_with_harness_flag counts "
                        "cases with each harness flag and overlaps it.",
        "results": results,
        "per_type": per_type,
        "failures": failures,
        "replays_and_step_checks": [
            {"name": "Step-level screen (Kitaru model-swap analyzer)",
             "reference": "sonnet-5.5, first prompt",
             "method": "250 recorded Sonnet 5.5 model calls replayed against each candidate with the same inputs; "
                       "the candidate's next step is compared with Sonnet's. A second Sonnet replay is the noise "
                       "floor. Full-run columns are each model's first-prompt accuracy on all 252 cases paired "
                       "against Sonnet.",
             "noise_floor": {"sonnet_same_tool_as_its_own_recording": comp["noise"]["tool_choice_A"]},
             "spearman_rank_correlation_with_full_runs": {k: round(v, 4) for k, v in comp["spearman"].items()},
             "holds_definition": "full-run accuracy at most 5 points below Sonnet 5.5",
             "models_that_hold": [bare(m) for m in comp["holders"]],
             "cheapest_model_that_holds": bare(comp["cheapest_holder"]),
             "top3_by_same_tool": [bare(m) for m in comp["finalists"]["tool_choice"]["top3"]],
             "top3_that_hold": [bare(m) for m in comp["finalists"]["tool_choice"]["holders_in_top3"]],
             "rank_of_cheapest_holder_by_same_tool": comp["finalists"]["tool_choice"]["cheapest_holder_rank"],
             "rows": step_rows,
             "spend_usd": round(sum(float(v) for v in comp["spent"].values()), 2)},
            {"name": "Full replay in Kitaru (record, then swap the model)",
             "reference": "sonnet-5.5, first prompt",
             "method": "48 cases recorded with Sonnet 5.5 through Kitaru; each candidate replayed the same cases end "
                       "to end through Kitaru experiments with a model override, with the same simulator and "
                       "judges. Paired bootstrap on the same cases. Haiku has n=47: one baseline case failed to "
                       "record cleanly.",
             "rows": full_replays,
             "spend_usd": 9.11},
            {"name": "Kitaru analyzer rerun after the fixes",
             "method": "The same step-level screen re-run on the updated analyzer (blind judge with order-swapped "
                       "recheck, held-out best mix), replay/out/underwritingA2 and B2. Same conclusion: a filter, "
                       "not a picker.",
             "rows": None, "rows_note": "Raw analyzer reports only (report.json); not summarized into a table.",
             "spend_usd": 15.62},
        ],
        "memorization_probe": {
            "method": "24 cases whose answers depend on the insurer's synthetic appetite table, asked of every model "
                      "with no tools and no data (company profile and question only).",
            "per_model": {bare(k): {"n": v["n"], "correct": v["correct"]} for k, v in probe.items()},
            "summary": "Product recommendations: 0 of 72 correct across models. Appetite checks: 41 of 216, nearly all "
                       "lodging and lessor businesses that the guidelines decline for fire risk, which a model can "
                       "reason out. No sign of memorization.",
        },
    }

    fp = lambda m: acc("first_prompt_all_cases", m)  # noqa: E731
    sh = lambda m: acc("shared_rewritten_prompt_held_out", m)  # noqa: E731
    export["headline_findings"] = [
        {"finding": f"With one prompt written once, accuracy ranged from {fp('gpt-oss-120b')['accuracy']:.4f} "
                    f"(gpt-oss-120b) to {fp('deepseek-v4-pro')['accuracy']:.4f} (DeepSeek V4 Pro) on 252 cases, and "
                    f"cost per correct decision from {fp('gpt-6-luna')['cost_per_correct_cents']}¢ to "
                    f"{fp('glm-5.3')['cost_per_correct_cents']}¢.",
         "numbers": ["results.first_prompt_all_cases[model=gpt-oss-120b].accuracy",
                     "results.first_prompt_all_cases[model=deepseek-v4-pro].accuracy",
                     "results.first_prompt_all_cases[model=gpt-6-luna].cost_per_correct_cents",
                     "results.first_prompt_all_cases[model=glm-5.3].cost_per_correct_cents"]},
        {"finding": "One rewritten prompt, shared unchanged, lifted 10 of the 11 other models on 168 held-out cases, "
                    "and 9 of 12 models scored between "
                    f"{sh('opus-5.5')['accuracy']:.4f} and "
                    f"{sh('sonnet-5.5')['accuracy']:.4f}.",
         "numbers": ["results.shared_rewritten_prompt_held_out[*].paired_vs.delta_points",
                     "results.shared_rewritten_prompt_held_out[model=opus-5.5].accuracy",
                     "results.shared_rewritten_prompt_held_out[model=sonnet-5.5].accuracy"]},
        {"finding": f"Under the shared prompt, Claude Haiku 5.5 got {sh('haiku-5.5')['correct']}/{sh('haiku-5.5')['n']} "
                    f"right at {sh('haiku-5.5')['cost_per_correct_cents']}¢ per correct decision, against Claude Opus "
                    f"5.5's {sh('opus-5.5')['correct']}/{sh('opus-5.5')['n']} at {sh('opus-5.5')['cost_per_correct_cents']}¢.",
         "numbers": ["results.shared_rewritten_prompt_held_out[model=haiku-5.5]",
                     "results.shared_rewritten_prompt_held_out[model=opus-5.5]"]},
        {"finding": "Running Sonnet 5.5 again with nothing changed moved its held-out accuracy by "
                    f"{noise['delta_points']} points (95% CI {noise['ci95_points']}), while lowering its reasoning "
                    f"effort to low moved it by {acc('effort_low_held_out', 'sonnet-5.5')['paired_vs']['delta_points']} points.",
         "numbers": ["noise.size_points", "results.effort_low_held_out[model=sonnet-5.5].paired_vs.delta_points"]},
        {"finding": "A cheap step-level screen ranked usefully but could not pick: its top 3 by same-tool agreement all "
                    "held Sonnet's accuracy, yet it ranked the cheapest model that holds "
                    f"{comp['finalists']['tool_choice']['cheapest_holder_rank']}th of 12, and Sonnet matched its own "
                    f"recorded tool only {comp['noise']['tool_choice_A']} of the time.",
         "numbers": ["replays_and_step_checks[0].top3_that_hold", "replays_and_step_checks[0].rank_of_cheapest_holder_by_same_tool",
                     "replays_and_step_checks[0].noise_floor"]},
        {"finding": "In the Kitaru full replay of 48 recorded cases, only DeepSeek V4 Pro's paired difference against "
                    "Sonnet 5.5 cleared zero.",
         "numbers": ["replays_and_step_checks[1].rows"]},
    ]
    export["limitations"] = [
        "One run per case per model and condition; differences under about 3 points are within run-to-run noise.",
        "The insurer's environment is reconstructed from published traces; 128 of 380 cases were dropped because the "
        "rebuilt environment did not reproduce their reference answer.",
        "The underwriter is simulated (Claude Haiku 5.5), not a person.",
        "Grading is by LLM judges validated against Snorkel's labels at 87.5-90.0% agreement per judge (n=150-160); "
        "the combined panel was not validated as a unit.",
        "Three judges (GPT-6 Luna, Claude Haiku 5.5, GPT-6.1 Sol) are also candidates; re-grading by other judges "
        "moved them by -0.8 to +1.6 points.",
        "The first-run system prompt was written once and not tuned for any model; first-run rankings largely reflect "
        "prompt fit.",
        "Prompt tuning: one optimizer (Opus 5.5), at most 2 rounds, 84 learning cases, one held-out run per tuned "
        "prompt. Five models were not tuned on their own (GPT-6 Luna: no rewrite improved its learning score; GLM 5.3, "
        "DeepSeek V4.1 Flash, MiniMax-M3, Qwen3.8 27B: only the shared prompt was run).",
        "The shared prompt was tuned on a Claude model and may favor Claude models.",
        "Effort settings were only tested on the five closed models.",
        "Prices are list prices on 2026-10-19; open-weight prices are from an unverified table, and open-weight "
        "models ran on one commercial inference provider (prices and behavior vary by provider).",
        "The failure categories 'final_answer_asks_for_information', 'empty_final_answer' and 'wrong_decision' are a "
        "text-pattern classification of wrong answers, not a judged label.",
        "The Kitaru full replay covers 48 cases; most of its intervals are wide.",
        "The step-level screen and full replay both use the first prompt; we did not repeat them under the rewritten "
        "prompt.",
    ]
    export["public_safety"] = [
        {"item": "Inference provider name for the open-weight models",
         "why": "Not named publicly until providers have seen their results; replaced by the neutral label provider-a "
                "everywhere (model keys, file names, this file).",
         "where_in_file": "models[*].provider_label"},
        {"item": "Unverified open-weight prices",
         "why": "Taken from third-party listings; publish only as 'list prices at the time, unverified' or re-check.",
         "where_in_file": "models[*].price_note"},
        {"item": "Internal file paths and repo name",
         "why": "The original research repository is private; paths in this file are relative to this benchmark's "
                "directory and the commit is for traceability only.",
         "where_in_file": "meta.code_location, meta.harness_git_commit, method strings"},
        {"item": "Model names for unreleased or renamed models",
         "why": "None known; check display names against vendor naming at publication time.",
         "where_in_file": "models[*].display_name"},
        {"item": "Customer data", "why": "None: Snorkel's companies are fictional; examples are paraphrased.",
         "where_in_file": "failures[*].example"},
    ]
    export["inconsistencies"] = INCONSISTENCIES
    json.dump(export, open(OUT, "w"), indent=1, ensure_ascii=False)
    print(OUT)


if __name__ == "__main__":
    main()
