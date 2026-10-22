"""Collect per-episode rows for the baseline and every replay experiment from a Kitaru server.

  KITARU_API_URL=... TAU2_KITARU_AGENT_ID=... uv run python collect_replays.py      # writes results/replays.jsonl

Reads only (no model calls). One row per episode: the arm, the tau2 case and task, the replay and
session status, tau2's reward from the episode output, the answering model(s) seen on the
session's llm_call nodes, Kitaru's recorded agent cost and token usage, and tau2's user-simulator cost.
"""
import asyncio
import json
import os

from kitaru.api_models.v1.experiment import ExperimentListParams
from kitaru.api_models.v1.filter import FilterCondition, FilterOp
from kitaru.api_models.v1.replay import ReplayListParams
from kitaru.api_models.v1.experiment_run import ExperimentRunListParams
from kitaru.api_models.v1.session import SessionListParams
from kitaru.client import KitaruAPIClient

HERE = os.path.dirname(os.path.abspath(__file__))
# The id of the tau2-telecom-live agent on your Kitaru server (`kitaru agent list`). The published
# run's id was 01a163cc-98e4-7c12-9ec3-f9d86934690a on a local server.
AGENT_ID = os.environ.get("TAU2_KITARU_AGENT_ID", "01a163cc-98e4-7c12-9ec3-f9d86934690a")


def outcome_of(outputs):
    if isinstance(outputs, str):
        try:
            outputs = json.loads(outputs)
        except ValueError:
            return None
    return outputs if isinstance(outputs, dict) and isinstance(outputs.get("tau2"), dict) else None


async def session_row(client, session_id):
    item = await client.sessions.get_with_nodes(session_id)
    s = item.session
    llm = [n for n in item.nodes if n.node_type.value == "llm_call"]
    tools = [n.tool_name or n.name for n in item.nodes if n.node_type.value == "tool_call"]
    out = outcome_of(s.outputs)
    tok = s.tokens
    return {
        "session_id": str(s.id), "session_status": s.status.value, "session_error": (s.error or "")[:300] or None,
        "case": out["case"] if out else None, "task_id": out["tau2"]["task_id"] if out else None,
        "reward": out["tau2"]["reward"] if out else None,
        "termination_reason": out["tau2"]["termination_reason"] if out else None,
        "user_cost_usd": out["tau2"]["user_cost_usd"] if out else None,
        "tau2_messages": out["tau2"]["messages"] if out else None,
        "models_answered": sorted({n.model for n in llm if n.model}),
        "llm_calls": s.llm_call_count, "tool_calls": s.tool_call_count, "tools_called": tools,
        "agent_cost_usd": str(s.cost) if s.cost is not None else None,
        "input_tokens": tok.input_tokens if tok else None, "cached_input_tokens": tok.cached_input_tokens if tok else None,
        "output_tokens": tok.output_tokens if tok else None, "reasoning_tokens": tok.reasoning_tokens if tok else None,
        "session_name": s.name,
    }


async def main():
    rows = []
    async with KitaruAPIClient() as client:
        base = SessionListParams(filter=FilterCondition(field="agent_id", op=FilterOp.EQ, value=AGENT_ID), size=500)
        async for s in client.sessions.iter(base):
            if s.name and s.name.endswith(" baseline") and s.name.startswith("tau2 telecom case "):
                rows.append({"arm": "baseline_gpt-5.2_recorded", "override_model": None, "agent_version": 1,
                             "replay_id": None, "baseline_session_id": None, **await session_row(client, s.id)})
        async for exp in client.experiments.iter(ExperimentListParams(size=100)):
            if not exp.name.startswith("tau2-"):
                continue
            runs = ExperimentRunListParams(filter=FilterCondition(field="experiment_id", op=FilterOp.EQ, value=str(exp.id)), size=100)
            async for run in client.experiment_runs.iter(runs):
                version = await client.agent_versions.get(run.agent_version_id)
                params = ReplayListParams(filter=FilterCondition(field="experiment_run_id", op=FilterOp.EQ, value=str(run.id)), size=500)
                async for rp in client.replays.iter(params):
                    row = {"arm": exp.name.removeprefix("tau2-"), "experiment_id": str(exp.id), "experiment_run_id": str(run.id),
                           "override_model": (rp.override.model if rp.override else None), "agent_version": version.version,
                           "replay_id": str(rp.id), "replay_status": rp.status.value, "replay_error": (rp.error or "")[:300] or None,
                           "baseline_session_id": str(rp.baseline_session_id)}
                    if rp.result_session_id:
                        row.update(await session_row(client, rp.result_session_id))
                    else:
                        base_row = await session_row(client, rp.baseline_session_id)
                        row.update({"case": base_row["case"], "task_id": base_row["task_id"], "reward": None,
                                    "session_status": None})
                    rows.append(row)
    os.makedirs(os.path.join(HERE, "results"), exist_ok=True)
    with open(os.path.join(HERE, "results", "replays.jsonl"), "w") as f:
        for r in sorted(rows, key=lambda r: (r["arm"], r["case"] if r["case"] is not None else -1)):
            f.write(json.dumps(r) + "\n")
    print(len(rows), "rows")


if __name__ == "__main__":
    asyncio.run(main())
