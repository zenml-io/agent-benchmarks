"""Step-level replay of the underwriting benchmark through the Kitaru model-swap analyzer (zenml-io/kitaru#1327).

  <kitaru venv>/bin/python replay/swap_underwriting.py underwriting --candidates a,b,... --tag A [--cap 25] [--responses]

A copy of the Haiku Tax benchmark's step-level calibration script pointed at this benchmark's transcripts: feeds the recorded
Sonnet 5.5 transcripts (results/transcripts/sonnet-5.5) to the PR's own analyzer code, unchanged: sessions are
built in memory instead of fetched from a Kitaru server, and everything after that (request rebuilding, sampling,
candidate calls, judge, report) is the plugin's. Candidates are live endpoints; Jev is the judge. Writes
replay/out/<use_case><tag>/{report.json,insights.json,calls.jsonl}. Keys come from the environment only.
"""
import argparse
import asyncio
import glob
import json
import os
import sys
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace

import kitaru_model_swap.analyzer as A
from kitaru.api_models.v1.session import TokenUsage
from kitaru.api_models.v1.session_node import NodeStatus, NodeType, SessionNodeResponse
from kitaru_model_swap.params import ModelSwapParams

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
from models_client import models as M  # noqa: E402

ANTHROPIC = ("https://api.anthropic.com/v1", "EVAL_ANTHROPIC_API_KEY")
INCUMBENT = "sonnet-5.5"
RESPONSES = "--responses" in sys.argv
CANDIDATES = {  # key -> (open weights, lab country)
    "sonnet-5.5": (False, "US"), "opus-5.5": (False, "US"), "haiku-5.5": (False, "US"),
    "gpt-6-luna": (False, "US"), "gpt-6.1-sol": (False, "US"),
    "deepseek-v4.1-flash@provider-a": (True, "CN"), "deepseek-v4-pro@provider-a": (True, "CN"),
    "glm-5.3@provider-a": (True, "CN"), "glm-5.3-flash@provider-a": (True, "CN"),  # the analyzer takes at most 8
    # candidates per run, so the calibration runs two batches (A: the first 8, B: Sonnet plus the rest)
    "gpt-oss-120b@provider-a": (True, "US"), "qwen3.8-27b@provider-a": (True, "CN"), "minimax-m3@provider-a": (True, "CN"),
}


def candidate(key):
    api, ep, model = M.endpoint(key)
    base, key_env = ANTHROPIC if api == "anthropic" else ep[:2]
    pin, pcached, pout = M.MODELS[key][3]
    opened, country = CANDIDATES[key]
    return {"name": key, "base_url": base, "model": model, "api_key_env": key_env, "reference": key == INCUMBENT,
            "open_weights": opened, "origin": {"lab_country": country, "host": base.split("/")[2]},
            "price": {"input_per_mtok": str(pin), "cached_input_per_mtok": str(pcached), "output_per_mtok": str(pout)},
            # GPT-6 rejects function tools with reasoning on /chat/completions. The first calibration runs (Oct 21)
            # used reasoning off for Luna and could not run Sol; with --responses, GPT-6 goes through the Responses
            # API (kitaru#1327 follow-up) with default reasoning, as in its full runs.
            "provider_settings": {"max_tokens": 4096, "timeout_seconds": 180, "max_retries": 3,
                                  **(({"api": "responses"} if RESPONSES else {"reasoning_effort": "none"})
                                     if key.startswith("gpt-6") else {})}}


def sessions(use_case):
    """One session per recorded task; one llm_call node per assistant turn."""
    pin, pcached, pout = M.MODELS[INCUMBENT][3]
    out, task_of = [], {}
    for path in sorted(glob.glob(os.path.join(ROOT, "results", "transcripts", INCUMBENT, "*.json"))):
        rec = json.load(open(path))
        sid = uuid.uuid5(uuid.NAMESPACE_URL, f"{use_case}/{rec['task']}")
        task_of[str(sid)] = rec["task"]
        msgs = rec["messages"]
        usages = iter([c for c in rec["calls"] if "error" not in c])
        nodes = []
        for i, m in enumerate(msgs):
            if m["role"] != "assistant" or i in rec.get("skip_nodes", ()):
                continue
            u = next(usages, {})
            inp, cached, outp = u.get("input", 0), u.get("cached", 0), u.get("output", 0)
            cost = (Decimal(inp - cached) * Decimal(str(pin)) + Decimal(cached) * Decimal(str(pcached))
                    + Decimal(outp) * Decimal(str(pout))) / Decimal(1_000_000)
            nodes.append(SessionNodeResponse.model_construct(
                id=uuid.uuid5(sid, str(i)), session_id=sid, external_id=f"{rec['task']}#{i}", links=[],
                node_type=NodeType.LLM_CALL, name="agent", status=NodeStatus.COMPLETED,
                inputs={"messages": msgs[:i], "tools": rec["tools"]}, outputs=m,
                model=M.endpoint(INCUMBENT)[2], requested_model=M.endpoint(INCUMBENT)[2],
                tokens=TokenUsage(input_tokens=inp, cached_input_tokens=cached, output_tokens=outp),
                cost=cost, attributes=None, metadata={}, model_params=None, reasoning_selectors=[]))
        out.append(SimpleNamespace(session=SimpleNamespace(id=sid, started_at=datetime.now(timezone.utc)), nodes=nodes))
    return out, task_of


class FakeClient:
    """Stands in for KitaruAPIClient: serves the in-memory sessions."""

    def __init__(self, by_id):
        async def get_with_nodes(i):
            return by_id[i]
        self.sessions = SimpleNamespace(get_with_nodes=get_with_nodes)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("use_case")
    ap.add_argument("--max-calls", type=int, default=250)
    ap.add_argument("--smoke", action="store_true")
    ap.add_argument("--candidates", default=",".join(CANDIDATES))
    ap.add_argument("--cap", default="60")
    ap.add_argument("--tag", default="")
    ap.add_argument("--responses", action="store_true", help="GPT-6 through the Responses API")
    a = ap.parse_args()
    sess, task_of = sessions(a.use_case)
    if a.smoke:
        sess = sess[:2]
    by_id = {s.session.id: s for s in sess}
    params = ModelSwapParams.model_validate({
        "candidates": [candidate(k) for k in a.candidates.split(",")],
        "judge": {"kind": "jev", "api_key_env": "JEV_API_KEY", "price": {"input_per_mtok": "0.042",
                                                                        "output_per_mtok": "0"}},
        "max_calls": 3 if a.smoke else a.max_calls, "max_spend_usd": a.cap, "concurrency": 32,
        "sessions_per_month": 30000, "max_disagreements": 500,
        "excluded_origins": {}})
    # The analyzer caps its time budget at 840 s to fit Kitaru's task timeout; this offline run has no such timeout.
    params = params.model_copy(update={"time_budget_seconds": 3600})
    captured = {}
    real_build_report = A.build_report

    def build_report(*args, **kw):
        captured["results"] = args[3]
        captured["report"] = real_build_report(*args, **kw)
        return captured["report"]

    async def no_dashboard(_client):
        return None

    A.KitaruAPIClient = lambda: FakeClient(by_id)
    A.build_report = build_report
    A._get_dashboard_url = no_dashboard
    insights = asyncio.run(A.run_model_swap(list(by_id), params))
    d = os.path.join(ROOT, "replay", "out", a.use_case + ("_smoke" if a.smoke else "") + a.tag)
    os.makedirs(d, exist_ok=True)
    json.dump(captured["report"], open(os.path.join(d, "report.json"), "w"), indent=1, default=str)
    json.dump([i.model_dump(mode="json") for i in insights], open(os.path.join(d, "insights.json"), "w"), indent=1)
    with open(os.path.join(d, "calls.jsonl"), "w") as f:
        for r in captured["results"]:
            rep = r.reply
            f.write(json.dumps({
                "task": task_of[str(r.call.session_id)], "node": str(r.call.node_id), "candidate": r.candidate,
                "attempt": r.attempt, "not_run": r.not_run, "agreement": r.agreement,
                "cost": str(r.cost) if r.cost is not None else None,
                "judge_equivalent": r.judge_equivalent, "judge_p": r.judge_probability,
                "recorded": [[c.name, c.arguments] for c in r.call.request.recorded.tool_calls],
                "recorded_text": r.call.request.recorded.text,
                "reply": None if rep is None else {"tools": [[c.name, c.arguments] for c in rep.tool_calls],
                                                   "text": rep.text, "failure": rep.failure,
                                                   "failure_detail": (rep.failure_detail or "")[:300],
                                                   "latency": rep.latency_seconds},
            }, default=str) + "\n")
    rep = captured["report"]
    print("spent", rep.get("spent_usd") or rep.get("spend"), "stopped_early", rep.get("stopped_early"))
    for c in rep["candidates"]:
        print(f"{c['name']:28} tool {c.get('tool_choice_rate')} exact {c.get('agreement_rate')} "
              f"fail {c.get('failure_rate')} cost/call {c['cost']['per_call_usd']}")
    for b in rep.get("best_for", []):
        print("BEST", b)


if __name__ == "__main__":
    main()
