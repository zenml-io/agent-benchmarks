"""Step-level model-swap check (kitaru-model-swap, zenml-io/kitaru#1327) on public recorded tau2-bench Telecom runs.

  uv run --extra step-check python harness/step_check/swap_run.py \
      --import-id IMPORT_ID [--max-calls 160] [--cap 20] [--dry-run] [--candidates FILE] [--out DIR]

Sessions come from a Kitaru server (KITARU_API_URL or the stored login) that holds the recorded
gpt-5.2-2025-12-11 runs imported from Exgentic/agent-llm-traces-v2 (tool_calling harness, tau2_telecom).
The analyzer runs unchanged, in this process instead of a worker task, so its full result is written
here (a worker task result is capped at 1 MB, which a full report with disagreements exceeds).
Writes harness/step_check/out/{report.json,insights.json,calls.jsonl}. Keys come from the environment only;
a candidate's base_url may name an environment variable (${OPENAI_COMPAT_BASE_URL_PROVIDER_A}), expanded here.
"""
import argparse
import asyncio
import json
import os

import kitaru_model_swap.analyzer as A
from kitaru.api_models.v1.filter import FilterCondition, FilterOp
from kitaru.api_models.v1.session import SessionListParams
from kitaru.client import KitaruAPIClient
from kitaru_model_swap.params import ModelSwapParams

HERE = os.path.dirname(os.path.abspath(__file__))


async def import_sessions(import_id):
    """Return the import's session IDs and each session's source run id (Exgentic session_id)."""
    params = SessionListParams(
        filter=FilterCondition(field="import_id", op=FilterOp.EQ, value=import_id), size=1000)
    async with KitaruAPIClient() as client:
        sessions = [s async for s in client.sessions.iter(params)]
    return [s.id for s in sessions], {str(s.id): s.external_id.rsplit("/", 1)[-1] for s in sessions}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--import-id", required=True)
    ap.add_argument("--max-calls", type=int, default=160)
    ap.add_argument("--cap", default="20")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--out", default=os.path.join(HERE, "out"))
    ap.add_argument("--candidates", default=os.path.join(HERE, "candidates.json"))
    a = ap.parse_args()
    ids, run_of = asyncio.run(import_sessions(a.import_id))
    params = ModelSwapParams.model_validate({
        "candidates": [dict(c, base_url=os.path.expandvars(c["base_url"])) for c in json.load(open(a.candidates))],
        "dry_run": a.dry_run, "max_calls": a.max_calls, "max_spend_usd": a.cap,
        "concurrency": 16, "max_disagreements": 200})
    # This run has no worker task timeout, so it does not need the analyzer's 840 s ceiling.
    params = params.model_copy(update={"time_budget_seconds": 3000})
    captured = {}
    real_build_report = A.build_report

    def build_report(*args, **kw):
        captured["results"] = args[3]
        captured["report"] = real_build_report(*args, **kw)
        return captured["report"]

    A.build_report = build_report
    insights = asyncio.run(A.run_model_swap(ids, params))
    os.makedirs(a.out, exist_ok=True)
    json.dump(captured["report"], open(os.path.join(a.out, "report.json"), "w"), indent=1, default=str)
    json.dump([i.model_dump(mode="json") for i in insights], open(os.path.join(a.out, "insights.json"), "w"), indent=1)
    with open(os.path.join(a.out, "calls.jsonl"), "w") as f:
        for r in captured.get("results") or []:
            rep = r.reply
            f.write(json.dumps({
                "run": run_of.get(str(r.call.session_id)), "node": str(r.call.node_id), "candidate": r.candidate,
                "attempt": r.attempt, "not_run": r.not_run, "agreement": r.agreement,
                "cost": str(r.cost) if r.cost is not None else None,
                "recorded": [[c.name, c.arguments] for c in r.call.request.recorded.tool_calls],
                "recorded_text": r.call.request.recorded.text,
                "reply": None if rep is None else {"tools": [[c.name, c.arguments] for c in rep.tool_calls],
                                                   "text": rep.text, "failure": rep.failure,
                                                   "failure_detail": (rep.failure_detail or "")[:300],
                                                   "latency": rep.latency_seconds},
            }, default=str) + "\n")
    rep = captured["report"]
    print("spent", rep.get("spent_usd"), "stopped_early", rep.get("stopped_early"))
    for c in rep["candidates"]:
        print(f"{c['name']:28} tool {c.get('tool_choice_rate')} exact {c.get('agreement_rate')} "
              f"fail {c.get('failure_rate')} cost/call {(c.get('cost') or {}).get('per_call_usd')} "
              f"estimate {(c.get('estimate') or {}).get('spend_usd')}")


if __name__ == "__main__":
    main()
