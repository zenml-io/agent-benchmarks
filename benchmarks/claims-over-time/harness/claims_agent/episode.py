"""Run the claims agent on one appeal and print one JSON result row.

From the directory that contains this package:

    CLAIMS_WORK_DIR=... python -m claims_agent.episode MN25-12345 --local   # plain PydanticAI, no Kitaru
    CLAIMS_WORK_DIR=... KITARU_AGENT_ID=... python -m claims_agent.episode MN25-12345   # recorded as a Kitaru session

Under a Kitaru worker (session run, replay or experiment) the appeal comes from the task input,
"Review appeal <id>.", and the row is also written as the task result.
"""

import argparse
import asyncio
import hashlib
import json
import os
import re
import time
import uuid
from typing import Any

from pydantic_ai import Agent, capture_run_messages
from pydantic_ai.messages import ModelMessage, ModelMessagesTypeAdapter, ModelResponse, ToolCallPart
from pydantic_ai.usage import UsageLimits

from .agent import HERE, Env, build_agent, load_config, work_dir

os.environ.setdefault("PYDANTIC_AI_NO_BANNER", "1")

USER_MESSAGE = "Review appeal {case_id}."
CASE_IN_INPUT = re.compile(r"Review appeal (\S+?)\.?(?:\"|$)")


def case_from_task() -> str | None:
    from kitaru.task import get_task_inputs

    inputs = get_task_inputs()
    if inputs is None:
        return None
    m = CASE_IN_INPUT.search(inputs if isinstance(inputs, str) else json.dumps(inputs))
    if not m:
        raise SystemExit(f"no 'Review appeal <id>.' in the task input: {inputs!r}"[:300])
    return m.group(1)


def version_hash() -> str:
    """A short hash of this package's files, so rows from two copies of the agent can be told apart."""
    digest = hashlib.sha256()
    for path in sorted(HERE.iterdir()):
        if path.is_file() and path.suffix in (".py", ".md", ".json", ".toml"):
            digest.update(path.name.encode() + b"\0" + path.read_bytes())
    return digest.hexdigest()[:12]


def summarize(messages: list[ModelMessage]) -> dict[str, Any]:
    responses = [m for m in messages if isinstance(m, ModelResponse)]
    costs = []
    for r in responses:
        try:
            costs.append(float(r.cost().total_price))
        except Exception:  # noqa: BLE001
            costs.append(None)  # no price known for this model (for example a self-hosted one)
    return {
        "turns": len(responses),
        "calls": [{"name": p.tool_name, "args": p.args_as_dict()} for r in responses for p in r.parts if isinstance(p, ToolCallPart)],
        "usage": {"input_tokens": sum(r.usage.input_tokens for r in responses),
                  "cache_read_tokens": sum(r.usage.cache_read_tokens for r in responses),
                  "output_tokens": sum(r.usage.output_tokens for r in responses),
                  "reasoning_tokens": sum(r.usage.details.get("reasoning_tokens", 0) for r in responses)},
        "cost_usd": sum(costs) if costs and None not in costs else None,
        "models": sorted({r.model_name for r in responses if r.model_name}),
    }


async def run_episode(case_id: str, kitaru: bool) -> dict[str, Any]:
    config = load_config()
    seen: set[str] = set()
    agent: Agent[None, dict[str, Any]] = build_agent(Env(work_dir()), case_id, seen, config)
    if kitaru:
        from kitaru_pydantic_ai import KitaruAgent

        ids = {k: uuid.UUID(os.environ[v]) for k, v in (("agent_id", "KITARU_AGENT_ID"), ("agent_version_id", "KITARU_AGENT_VERSION_ID"))
               if os.environ.get(v)}
        agent = KitaruAgent(agent, session_name=os.environ.get("KITARU_SESSION_NAME") or f"claims appeal {case_id}", **ids)
    final, run_error, t0 = None, None, time.time()
    with capture_run_messages() as messages:
        try:
            result = await agent.run(USER_MESSAGE.format(case_id=case_id),
                                     usage_limits=UsageLimits(request_limit=config["request_limit"]))
            final = result.output
        except Exception as exc:  # noqa: BLE001
            run_error = repr(exc)[:500]
    return {"case_id": case_id, "final": final, **summarize(messages), "seen_precedents": sorted(seen),
            "seconds": round(time.time() - t0, 1), "run_error": run_error, "agent_version": version_hash(),
            "agent_dir": str(HERE), "transcript": json.loads(ModelMessagesTypeAdapter.dump_json(messages))}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("case_id", nargs="?", help="appeal id; read from the Kitaru task input when run by a worker")
    ap.add_argument("--local", action="store_true", help="run without Kitaru (no session is recorded)")
    a = ap.parse_args()
    in_task = bool(os.environ.get("KITARU_TASK_ID"))
    case_id = (case_from_task() if in_task else None) or a.case_id
    if not case_id:
        raise SystemExit("pass an appeal id")
    if not (a.local or in_task or os.environ.get("KITARU_AGENT_ID")):
        raise SystemExit("set KITARU_AGENT_ID to record a Kitaru session, or pass --local")
    row = asyncio.run(run_episode(case_id, kitaru=not a.local))
    text = json.dumps(row)
    if os.environ.get("KITARU_TASK_RESULT_PATH"):
        with open(os.environ["KITARU_TASK_RESULT_PATH"], "w") as f:
            f.write(text)
    print(text, flush=True)


if __name__ == "__main__":
    main()
