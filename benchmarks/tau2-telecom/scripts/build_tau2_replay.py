"""Build results/tau2-telecom-kitaru-replay.json from existing per-episode rows only (no model calls).

  python3 scripts/build_tau2_replay.py [--runs-dir DIR] [--step-check-dir DIR] [--out FILE]   # from benchmarks/tau2-telecom

Inputs (paths relative to benchmarks/tau2-telecom):
- results/runs/replay/replays.jsonl: one row per episode (harness/replay/collect_replays.py)
- results/runs/replay/baseline.jsonl: the baseline run log (cross-check)
- results/costs/replay.json: recorded spend
- results/runs/step_check/out{,_responses}/report.json: the earlier step check (screen vs outcome)
Paired differences use scripts/stats.py paired_delta (per-task bootstrap, 10000 resamples, seed 0).
"""
import argparse
import json
import os
import sys
from collections import Counter, defaultdict
from decimal import ROUND_HALF_EVEN, Decimal

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # benchmarks/tau2-telecom
sys.path.insert(0, os.path.join(HERE, "scripts"))
from stats import paired_delta  # noqa: E402

# Text in the export names the original location and commit (provenance), not this copy.
BENCH = "benchmarks/tau2-telecom-public/replay"
ORIGINAL_COMMIT = "b6ed9ae92115616fd69dbe50a0fe995a49c6b6a6"
RUNS_DIR = os.path.join(HERE, "results", "runs", "replay")
STEP_CHECK_DIR = os.path.join(HERE, "results", "runs", "step_check")
COSTS = os.path.join(HERE, "results", "costs", "replay.json")
OUT = os.path.join(HERE, "results", "tau2-telecom-kitaru-replay.json")
SLUG = "tau2-telecom-kitaru-replay"
BASE = "baseline_gpt-5.2_recorded"
NOISE = "noise_gpt-5_2"
TRANSFER = "transfer_to_human_agents"
# arm -> (model id sent, display name, vendor, weights, inference provider type, step-check candidate name)
ARMS = {
    BASE: ("gpt-5.2-2025-12-11", "GPT-5.2 (baseline recording)", "OpenAI", "closed", "vendor API", "gpt-5.2 (recorded model)"),
    NOISE: ("gpt-5.2-2025-12-11", "GPT-5.2 (rerun, no override)", "OpenAI", "closed", "vendor API", None),
    "prompt-escalation-rule": ("gpt-5.2-2025-12-11", "GPT-5.2 + escalation rule", "OpenAI", "closed", "vendor API", None),
    "gpt-5_6-sol": ("gpt-5.6-sol", "GPT-5.6 Sol", "OpenAI", "closed", "vendor API", "gpt-5.6-sol"),
    "gpt-5_6-luna": ("gpt-5.6-luna", "GPT-5.6 Luna", "OpenAI", "closed", "vendor API", "gpt-5.6-luna"),
    "gpt-5_4-mini": ("gpt-5.4-mini", "GPT-5.4 mini", "OpenAI", "closed", "vendor API", "gpt-5.4-mini"),
    "qwen3_8-27b": ("Qwen/Qwen3.8-27B", "Qwen3.8 27B", "Alibaba Qwen", "open", "commercial provider", "qwen3.8-27b"),
    "kimi-k3": ("moonshotai/Kimi-K3", "Kimi K3", "Moonshot AI", "open", "commercial provider", "kimi-k3"),
    "glm-5_3": ("zai-org/GLM-5.3", "GLM-5.3", "Z.ai", "open", "commercial provider", "glm-5.3"),
    "deepseek-v4_1-flash": ("deepseek-ai/DeepSeek-V4.1-Flash", "DeepSeek V4.1 Flash", "DeepSeek", "open", "commercial provider", "deepseek-v4.1-flash"),
}
# USD per 1M tokens (input, cached input, output) for models Kitaru could not price; benchmarks/haiku-tax/harness/models.py
# (checked 2026-10-19), which marks provider-a prices UNVERIFIED (third-party listings; cached input billed as input).
TABLE_PRICES = {"Qwen/Qwen3.8-27B": (0.45, 0.45, 3.00), "moonshotai/Kimi-K3": (3.00, 3.00, 15.00),
                "zai-org/GLM-5.3": (1.40, 1.40, 4.40), "deepseek-ai/DeepSeek-V4.1-Flash": (0.30, 0.30, 1.20)}
OPENAI_PRICES = {"gpt-5.2-2025-12-11": (1.75, 0.175, 14), "gpt-5.6-sol": None, "gpt-5.6-luna": None, "gpt-5.4-mini": None}


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


def agent_cost(row):
    """Kitaru's recorded cost for priced models; tokens x table price for models Kitaru could not price."""
    model = ARMS[row["arm"]][0]
    if model in TABLE_PRICES:
        pin, pcached, pout = TABLE_PRICES[model]
        inp, cached, out = row.get("input_tokens") or 0, row.get("cached_input_tokens") or 0, row.get("output_tokens") or 0
        return (Decimal(inp - cached) * Decimal(str(pin)) + Decimal(cached) * Decimal(str(pcached))
                + Decimal(out) * Decimal(str(pout))) / Decimal(1_000_000), "tokens x unverified table price"
    return (Decimal(row["agent_cost_usd"]) if row.get("agent_cost_usd") is not None else None), "Kitaru recorded cost"


def solved(row):
    return row.get("reward") == 1.0


def category(row):
    if row.get("reward") is None:
        return "no_graded_outcome"
    if solved(row):
        return None
    return "escalated_to_human_on_unsolved_task" if TRANSFER in (row.get("tools_called") or []) else "unsolved_without_escalation"


def git_commit(path):
    """The original repository commit that added this harness (the published copy is not a git checkout of it)."""
    return ORIGINAL_COMMIT


def task_type(task_id):
    return task_id.split("]")[0].strip("[") if task_id else "unknown"


def main():
    rows = [json.loads(line) for line in open(os.path.join(RUNS_DIR, "replays.jsonl"))]
    by_arm = defaultdict(dict)
    for r in rows:  # one row per (arm, case); a later row for the same case replaces an earlier one
        if r.get("case") is not None:
            by_arm[r["arm"]][r["case"]] = r
    arms = [a for a in ARMS if a in by_arm]
    base_rows = {r["case"]: r for r in map(json.loads, open(os.path.join(RUNS_DIR, "baseline.jsonl")))}

    def episodes(arm):
        return [{"scenario": c, "v": int(solved(r))} for c, r in by_arm[arm].items()]

    def paired(arm, ref):
        res = paired_delta(episodes(arm), episodes(ref), key="v", n_boot=10000, seed=0)
        return {"reference": ref, "n": res["n"], "delta_points": q4(res["delta"] * 100),
                "ci95_points": [q4(res["lo"] * 100), q4(res["hi"] * 100)],
                "tasks_gained": res["flips_up"], "tasks_lost": res["flips_down"]}

    results, costs_by_arm = [], {}
    for arm in arms:
        g = list(by_arm[arm].values())
        n, k = len(g), sum(solved(r) for r in g)
        cost_parts = [agent_cost(r) for r in g]
        known = [c for c, _ in cost_parts if c is not None]
        agent_total = sum(known) if len(known) == n else None
        user_total = sum(Decimal(str(r["user_cost_usd"])) for r in g if r.get("user_cost_usd") is not None)
        costs_by_arm[arm] = (agent_total, user_total, {s for _, s in cost_parts})
        results.append({
            "model": arm, "model_id": ARMS[arm][0], "n": n, "correct": k, "accuracy": q4(k / n), "ci95": wilson(k, n),
            "cost_per_correct_cents": q4(agent_total / k * 100) if agent_total is not None and k else None,
            "cost_source": sorted({s for _, s in cost_parts})[0],
            "agent_cost_usd": float(agent_total.quantize(Decimal("0.000001"))) if agent_total is not None else None,
            "user_simulator_cost_usd": float(user_total.quantize(Decimal("0.000001"))),
            "mean_tokens_per_case": q4(sum((r.get("input_tokens") or 0) + (r.get("output_tokens") or 0) for r in g) / n),
            "mean_calls_per_case": q4(sum(r.get("llm_calls") or 0 for r in g) / n),
            "mean_tool_calls_per_case": q4(sum(r.get("tool_calls") or 0 for r in g) / n),
            "statuses": dict(sorted(Counter(f"session={r.get('session_status')}, replay={r.get('replay_status', 'n/a')}, termination={r.get('termination_reason')}" for r in g).items())),
            "failures": dict(sorted(Counter(category(r) for r in g if category(r)).items())),
            "transfers_in_solved_runs": sum(solved(r) and TRANSFER in (r.get("tools_called") or []) for r in g),
            "paired_vs": None if arm == BASE else paired(arm, BASE),
            "paired_vs_noise": None if arm in (BASE, NOISE) else paired(arm, NOISE),
        })

    per_type = {"live_full_runs": {}}
    for arm in arms:
        per_type["live_full_runs"][arm] = {}
        for t in sorted({task_type(r.get("task_id")) for r in by_arm[arm].values()}):
            g = [r for r in by_arm[arm].values() if task_type(r.get("task_id")) == t]
            k = sum(solved(r) for r in g)
            per_type["live_full_runs"][arm][t] = {"n": len(g), "correct": k, "accuracy": q4(k / len(g))}
    types = Counter(task_type(r.get("task_id")) for r in by_arm[BASE].values())

    failures = [
        {"category": "escalated_to_human_on_unsolved_task",
         "definition": "Unsolved episode (tau2 reward 0) in which the agent called transfer_to_human_agents. From the session's tool_call nodes, not text.",
         "counts": {a: sum(category(r) == "escalated_to_human_on_unsolved_task" for r in by_arm[a].values()) for a in arms},
         "example": "After several rounds of device checks the agent handed the customer to a human while a fix it could still apply remained."},
        {"category": "unsolved_without_escalation",
         "definition": "Unsolved episode (tau2 reward 0) with no transfer_to_human_agents call: the agent ended, or the user simulator ended, with the device or account still in the wrong state. From tool_call nodes.",
         "counts": {a: sum(category(r) == "unsolved_without_escalation" for r in by_arm[a].values()) for a in arms},
         "example": "The agent fixed one of the user's problems, the user confirmed the first symptom was gone, and the conversation ended with a second misconfiguration left in place."},
        {"category": "no_graded_outcome",
         "definition": "The replay or its session failed before tau2 graded the episode (provider error, process failure); counted as unsolved.",
         "counts": {a: sum(category(r) == "no_graded_outcome" for r in by_arm[a].values()) for a in arms},
         "example": "The candidate's provider returned an error mid-episode and the session failed."},
    ]

    # screen (step check) vs outcome (full replay)
    step = {}
    for d in ("out", "out_responses"):
        p = os.path.join(STEP_CHECK_DIR, d, "report.json")
        for c in json.load(open(p))["candidates"]:
            if c["answered"]:
                step[c["name"]] = c
    pairs = []
    for arm in arms:
        name = ARMS[arm][5]
        if name and name in step and arm != BASE:
            row = next(x for x in results if x["model"] == arm)
            pairs.append({"arm": arm, "step_tool_choice_rate": step[name]["tool_choice_rate"],
                          "step_tool_choice_n": step[name]["tool_choice_calls"],
                          "replay_accuracy": row["accuracy"], "replay_n": row["n"],
                          "replay_delta_vs_baseline_points": row["paired_vs"]["delta_points"],
                          "replay_delta_ci95_points": row["paired_vs"]["ci95_points"]})

    def ranks(v):
        order = sorted(range(len(v)), key=lambda i: v[i])
        r, i = [0.0] * len(v), 0
        while i < len(v):
            j = i
            while j + 1 < len(v) and v[order[j + 1]] == v[order[i]]:
                j += 1
            for x in range(i, j + 1):
                r[order[x]] = (i + j) / 2
            i = j + 1
        return r

    xs, ys = [p["step_tool_choice_rate"] for p in pairs], [p["replay_accuracy"] for p in pairs]
    rx, ry = ranks(xs), ranks(ys)
    mx, my = sum(rx) / len(rx), sum(ry) / len(ry)
    den = (sum((a - mx) ** 2 for a in rx) * sum((b - my) ** 2 for b in ry)) ** 0.5
    spearman = q4(sum((a - mx) * (b - my) for a, b in zip(rx, ry)) / den) if den else None

    costs = json.load(open(COSTS))
    best = max((r for r in results if r["model"] not in (BASE, NOISE, "prompt-escalation-rule")), key=lambda r: r["accuracy"])
    noise_row = next(r for r in results if r["model"] == NOISE)
    prompt_row = next(r for r in results if r["model"] == "prompt-escalation-rule")
    base_row = next(r for r in results if r["model"] == BASE)
    doc = {
        "meta": {
            "name": "Full Kitaru replays on tau2-bench Telecom: which model holds up?",
            "slug": SLUG,
            "question": "If you swap the model behind a tau2-bench Telecom support agent (or fix its prompt), does it solve more customer tasks end to end, and did Kitaru's cheap step screen predict which swaps would?",
            "domain": "Telecom technical support (agent with tools, simulated customer who runs device actions)",
            "status": "complete",
            "run_dates": {"baseline_recording": "2026-10-22", "replays": "2026-10-22"},
            "who_ran": "Hamza Tahir (ZenML), with Claude Code agents",
            "kitaru_version": "0.27.2+dev",
            "kitaru_details": {"server_and_worker": "zenml-io/kitaru branch feature/model-swap-analyzer at 0217140c9bd6fc1b0569abefbaea30be20a6fde4",
                               "adapter": "kitaru-pydantic-ai 0.3.1 (KitaruAgent) from the same checkout; PydanticAI 2.51.0",
                               "flow": "baseline sessions recorded live -> cohort (40 sessions) -> one Kitaru experiment per arm (model override or agent version, explicit passthrough tool policy, evaluator tau2-task-success@1) -> replays run by Kitaru workers"},
            "harness_git_commit": git_commit(BENCH),
            "harness_git_commit_note": None if git_commit(BENCH) else f"{BENCH} is not committed yet.",
            "code_location": BENCH,
            "total_spend_usd": None,
            "total_spend_usd_note": costs["note"] + " Parts: " + "; ".join(f"{c['what']}: {c['spent_usd'] if c['spent_usd'] is not None else 'not recorded'}" for c in costs["runs"]),
        },
        "dataset": {
            "source": "tau2-bench (Sierra Research), telecom domain, test split",
            "url": "https://github.com/sierra-research/tau2-bench",
            "version": "commit 05736c2 (2026-10-21)",
            "license": "MIT",
            "total_cases": 40, "kept_cases": len(by_arm[BASE]),
            "dropped_reason": "None dropped: every test-split task ran in every arm.",
            "split": {"test": len(by_arm[BASE])},
            "split_note": "tau2's own test split (data/tau2/domains/telecom/split_tasks.json). Nothing was tuned on it; the prompt-audit rule was written once from the failure pattern in the public Exgentic recordings and the tau2 manual, before any test-split result.",
            "types": [{"type": t, "count": types[t]} for t in sorted(types)],
            "types_note": "Type is the bracketed prefix of each tau2 task id.",
        },
        "models": [
            {"id": ARMS[a][0], "arm": a, "display_name": ARMS[a][1], "vendor": ARMS[a][2], "weights": ARMS[a][3],
             "inference_provider_type": ARMS[a][4],
             "price_per_mtok_input_usd": TABLE_PRICES[ARMS[a][0]][0] if ARMS[a][0] in TABLE_PRICES else None,
             "price_per_mtok_cached_input_usd": TABLE_PRICES[ARMS[a][0]][1] if ARMS[a][0] in TABLE_PRICES else None,
             "price_per_mtok_output_usd": TABLE_PRICES[ARMS[a][0]][2] if ARMS[a][0] in TABLE_PRICES else None,
             "price_date": "2026-10-19" if ARMS[a][0] in TABLE_PRICES else "2026-10-22",
             "price_note": ("UNVERIFIED third-party listing from benchmarks/haiku-tax/harness/models.py; Kitaru had no price for this model, so agent cost = tokens x this price." if ARMS[a][0] in TABLE_PRICES
                            else "Priced by Kitaru's adapter from its bundled genai-prices catalog on the run date (2026-10-22); per-token prices are not stored on the session, so they are null here."),
             **({"provider_private": "provider-a (via the local model_router.py)"} if ARMS[a][4] == "commercial provider" else {})}
            for a in arms],
        "setup": {
            "conditions": [{"name": a, "description": {
                BASE: "GPT-5.2 run live on each task (agent version 1); these 40 sessions are the Kitaru cohort every other arm replays.",
                NOISE: "Kitaru replay of each baseline session with no override (agent version 3, routed): the same model run again, the noise floor.",
                "prompt-escalation-rule": "Kitaru replay with agent version 2: GPT-5.2 plus one general rule from the prompt audit (prompt_addendum.txt).",
            }.get(a, f"Kitaru replay of each baseline session with the model overridden to {ARMS[a][0]} (agent version 3).")} for a in arms],
            "prompt_rewriting": {"method": "Prompt audit (kitaru-model-swap skill, step 2): the policy says to transfer only if a request cannot be handled and to 'try all the possible ways' but never defines when troubleshooting is exhausted. One general rule was appended to the agent instructions: work through every applicable manual section, have the user re-check after each change, check the account side, and transfer only when every step has failed or the manual says to escalate.",
                                 "text_file": f"{BENCH}/prompt_addendum.txt",
                                 "leakage_check": "Written before any test-split episode ran, from the failure pattern in the public Exgentic recordings (premature transfers) and the tau2 manual's structure; it contains no task ids, scenarios, device states or answers."},
            "tools": "tau2's 13 telecom agent tools as PydanticAI tools (schemas from tau2), plus send_message_to_user, whose result is the simulated user's reply. Device tools belong to the simulated user. Kitaru tool policy: explicit passthrough for every tool in every arm (the environment and simulator are local and side-effect free).",
            "user_simulator": "tau2's UserSimulator with gpt-4.1-2025-04-14 (tau2's default), unchanged across arms.",
            "limits": {"tau2_max_steps": 100, "agent_request_limit": 100, "agent_output_retries": 30, "episode_timeout_seconds": 1200},
            "agent_harness": "tau2's own Orchestrator runs each episode; the agent is one PydanticAI run wrapped in KitaruAgent, so one episode is one Kitaru session (tau2_kitaru_agent/episode.py).",
        },
        "grading": {
            "judges": [{"name": "tau2 evaluator (EvaluationType.ALL; communicate scoring set to tau2's original substring scorer, so grading uses no LLM)", "applies_to": "every arm"},
                       {"name": "Kitaru evaluator tau2-task-success@1", "applies_to": "every arm", "note": "Reads tau2's reward from the episode output; a session with no graded outcome scores 0."}],
            "tie_break": None, "tie_break_note": "No ranking ties broken.",
            "human_agreement": None, "human_agreement_note": "No LLM judge, so no human agreement to measure.",
            "self_grading_check": None, "self_grading_check_note": "No model graded any answer; tau2 grades from environment state.",
            "metrics": [
                {"name": "accuracy", "definition": "correct / n; correct = tau2 reward 1.0. Episodes without a graded outcome count as wrong."},
                {"name": "cost_per_correct_cents", "definition": "100 x (sum of agent model cost over all n episodes of the arm, solved or not) / correct. Agent cost is Kitaru's recorded session cost (adapter pricing with cached-input prices) for OpenAI models, and input/cached/output tokens x the unverified table price for open-weight models Kitaru could not price. User-simulator cost is reported separately (user_simulator_cost_usd) and excluded."},
                {"name": "paired_vs", "definition": "Arm minus reference on the same 40 tasks: mean per-task difference in solved (0/1), in points, with a 95% bootstrap interval (swapbench.stats.paired_delta, tasks resampled, 10000 resamples, seed 0); tasks_gained/lost count flips."},
            ],
        },
        "noise": {
            "method": "GPT-5.2 replayed with no override (noise_gpt-5_2) against its own baseline recording, same 40 tasks.",
            "size": {"noise_accuracy": noise_row["accuracy"], "baseline_accuracy": base_row["accuracy"], "paired": noise_row["paired_vs"]},
            "ci_method": "Wilson score 95% for accuracies; per-task bootstrap for paired differences.",
            "resamples": 10000,
            "tie_threshold": None,
            "tie_threshold_note": "A difference whose paired 95% interval includes 0 is reported as not distinguishable.",
        },
        "results": {"live_full_runs": results},
        "results_note": "One row per (arm, task). Every episode stays in n; episodes without a graded tau2 outcome count as wrong. No episodes were dropped. Replays interrupted by the server restart were retried by Kitaru (attempt 2); each task's final replay is used.",
        "per_type": per_type,
        "failures": failures,
        "replays_and_step_checks": [{
            "name": "step_screen_vs_full_replay",
            "description": "Does the earlier step check (Kitaru model-swap screen on the public recorded GPT-5.2 calls) rank models the way full replays do? Step agreement is the share of recorded tool choices a candidate repeated; replay accuracy is tau2 task success here.",
            "pairs": pairs,
            "spearman_step_vs_replay": spearman, "spearman_n": len(pairs),
            "note": "The step check resent public Exgentic recordings (different harness and user simulator) while replays ran this harness, so this compares rankings, not numbers.",
        }],
        "headline_findings": [],
        "limitations": [
            "40 tasks per arm and one episode per task, so accuracy intervals are wide (about +/-15 points); per-task paired intervals are reported for every comparison.",
            "The user simulator is an LLM (gpt-4.1); the noise arm measures how much outcomes move on a rerun with nothing changed.",
            "Replays start fresh episodes from each task (Kitaru replays the case, not the recorded conversation), so a replay is a new full run, not a step check.",
            "The agent harness is ours (PydanticAI with a send_message_to_user tool), not tau2's built-in LLM agent; numbers are not comparable to the tau2 leaderboard.",
            "Open-weight models ran on one commercial provider through a local router that strips a provider-specific response field; their costs use unverified prices.",
            "Model settings are provider defaults (no reasoning-effort tuning per model).",
            "The step-screen comparison uses different recordings (public Exgentic traces) from the replays.",
        ],
        "public_safety": [
            {"item": "Inference provider for open-weight models", "why": "Provider names stay private in these exports.", "where_in_file": "models[*].provider_private"},
            {"item": "Open-weight prices and costs", "why": "Unverified third-party prices.", "where_in_file": "models[weights=open].price_*, results.live_full_runs[*].cost_per_correct_cents for open models"},
            {"item": "Unreleased Kitaru features and bugs", "why": "Uses the unmerged model-swap branch; workarounds for kitaru#1339, #1344 and others are described in limitations and meta.", "where_in_file": "meta.kitaru_details"},
        ],
        "inconsistencies": [],
    }
    order = sorted((r for r in results if r["model"] not in (BASE,)), key=lambda r: -r["accuracy"])
    doc["headline_findings"] = [
        {"finding": f"{ARMS[best['model']][1]} solved the most tasks, ahead of the GPT-5.2 baseline on the same 40 tasks.",
         "numbers": [f"results.live_full_runs[model={best['model']}].accuracy", f"results.live_full_runs[model={best['model']}].paired_vs.delta_points",
                     f"results.live_full_runs[model={best['model']}].paired_vs.ci95_points", f"results.live_full_runs[model={BASE}].accuracy"]},
        {"finding": "GPT-5.2 rerun with nothing changed lands on the same accuracy but solves a different set of tasks, which sets the bar for every swap.",
         "numbers": [f"results.live_full_runs[model={NOISE}].accuracy", f"results.live_full_runs[model={NOISE}].paired_vs.tasks_gained", f"results.live_full_runs[model={NOISE}].paired_vs.tasks_lost"]},
        {"finding": "The prompt-audit rule (exhaust troubleshooting before transferring) did not measurably help GPT-5.2: its paired difference includes zero and unsolved tasks still ended in a transfer as often.",
         "numbers": ["results.live_full_runs[model=prompt-escalation-rule].paired_vs.delta_points", "results.live_full_runs[model=prompt-escalation-rule].paired_vs.ci95_points",
                     "failures[category=escalated_to_human_on_unsolved_task].counts"]},
        {"finding": "Models that lost tasks mostly lost them by handing the customer to a human: every unsolved GPT-5.6 Luna episode ended in a transfer.",
         "numbers": ["failures[category=escalated_to_human_on_unsolved_task].counts", "results.live_full_runs[model=gpt-5_6-luna].correct", "results.live_full_runs[model=gpt-5_6-luna].n"]},
        {"finding": "The cheap step screen did not rank models the way full replays did.",
         "numbers": ["replays_and_step_checks[name=step_screen_vs_full_replay].spearman_step_vs_replay", "replays_and_step_checks[name=step_screen_vs_full_replay].spearman_n"]},
    ]
    incons = doc["inconsistencies"]
    for c, b in base_rows.items():
        r = by_arm[BASE].get(c)
        if r and (b.get("tau2") or {}).get("reward") != r.get("reward"):
            incons.append({"where": "baseline.jsonl vs Kitaru session output", "case": c, "log": (b.get("tau2") or {}).get("reward"), "kitaru": r.get("reward")})
    incons.append({"where": "Exgentic public recordings (tau2-telecom-public-traces.json)", "claim": "GPT-5.2 accuracy on tau2-bench Telecom",
                   "data": f"0.5347 (54/101) in Exgentic's tool_calling harness on the base set vs {base_row['accuracy']} ({base_row['correct']}/{base_row['n']}) here on the test split; different harness, user simulator and task set."})
    zero = [a for a in arms if ARMS[a][0] in TABLE_PRICES]
    incons.append({"where": "Kitaru session cost", "claim": "session.cost is the session's model cost",
                   "data": f"Sessions of {', '.join(zero)} report cost 0 although every llm_call node's cost is null (no price): the rollup counts unpriced calls as 0."})
    with open(OUT, "w") as f:
        json.dump(doc, f, indent=1, ensure_ascii=False)
        f.write("\n")
    print("wrote", OUT)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs-dir", default=RUNS_DIR)
    ap.add_argument("--step-check-dir", default=STEP_CHECK_DIR)
    ap.add_argument("--out", default=OUT)
    a = ap.parse_args()
    RUNS_DIR, STEP_CHECK_DIR, OUT = a.runs_dir, a.step_check_dir, a.out
    main()
