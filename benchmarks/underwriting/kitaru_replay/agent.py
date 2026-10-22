"""The underwriting copilot as a Kitaru-recorded agent (a project-local adapter around harness/run.py).

  python kitaru_replay/agent.py --record <task_id>[,<task_id>...] [--model sonnet-5.5]   # record baselines directly
  python kitaru_replay/agent.py                                                         # as a Kitaru worker task

Runs harness/run.py's episode unchanged and records it as one Kitaru session: an llm_call node per copilot call
(OpenAI chat messages, tokens and list-price cost), a tool_call node per database tool, and a span node per simulated
underwriter reply. Under a replay it applies the replay's model override (keys are the harness's model keys, e.g.
{"sonnet-5.5": "deepseek-v4-pro@provider-a"}) and accepts only the passthrough tool policy: the tools are read-only
queries over a fixed SQLite file, so a live re-run sees the same data. The simulated underwriter runs live too, so a
replay is a fresh conversation with the same company, as in the benchmark. Grading is left to the evaluator
(kitaru_replay/evaluator.py); the task's reference answer goes in the session metadata.
"""
import argparse
import asyncio
import copy
import json
import os
import sys
import threading
import uuid
from datetime import UTC, datetime
from decimal import Decimal

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "harness"))
import run as H  # noqa: E402
from kitaru.api_models.v1.replay_config import PassthroughConfig  # noqa: E402
from kitaru.api_models.v1.session import (  # noqa: E402
    SessionCreateRequest, SessionOrigin, SessionStatus, SessionUpdateRequest, TokenUsage)
from kitaru.api_models.v1.session_node import (  # noqa: E402
    NodeStatus, NodeType, SessionNodeBatchRequest, SessionNodeCreateRequest)
from kitaru.client.api_client import KitaruAPIClient  # noqa: E402
from kitaru.task import get_task_id, get_task_inputs  # noqa: E402

FRAMEWORK, ADAPTER_VERSION, DEFAULT_MODEL = "underwriting-raw-http", "0.1", "sonnet-5.5"
TASKS = {t["id"]: t for t in json.load(open(os.path.join(H.ENV, "tasks.json")))}


class Recorder:
    """Wraps the harness's model, tool and simulator calls and collects them as session nodes."""

    def __init__(self, requested, model):
        self.requested, self.model, self.nodes, self.lock = requested, model, [], threading.Lock()

    def _add(self, **kw):
        with self.lock:
            kw.setdefault("external_id", f"n{len(self.nodes)}")
            self.nodes.append(SessionNodeCreateRequest(parent_external_id="root", attributes={}, **kw))

    def call_model(self, key, msgs, tools):
        start = datetime.now(UTC)
        try:
            msg, usage, lat, retries = H.M_call_model(key, msgs, tools)
        except RuntimeError as e:
            self._add(node_type=NodeType.LLM_CALL, name="copilot", status=NodeStatus.FAILED, error=str(e)[:500],
                      started_at=start, ended_at=datetime.now(UTC), inputs=copy.deepcopy(msgs), outputs=None,
                      requested_model=self.requested, model=H.M.endpoint(key)[2], model_provider=key)
            raise
        inp, cached, out = usage.get("input", 0), usage.get("cached", 0), usage.get("output", 0)
        reply = {k: v for k, v in msg.items() if not k.startswith("_") and k != "reasoning_content"}
        reply["role"] = "assistant"
        self._add(node_type=NodeType.LLM_CALL, name="copilot", status=NodeStatus.COMPLETED, started_at=start,
                  ended_at=datetime.now(UTC),
                  inputs=[{k: v for k, v in m.items() if not k.startswith("_")} for m in msgs], outputs=[reply],
                  input_text_selector=None, output_text_selector="/0/content", system_prompt_selector="/0/content",
                  requested_model=self.requested, model=H.M.endpoint(key)[2], model_provider=key,
                  tokens=TokenUsage(input_tokens=inp, cached_input_tokens=cached, output_tokens=out,
                                    reasoning_tokens=usage.get("reasoning", 0)),
                  cost=Decimal(str(round(H.M.cost(key, inp, cached, out), 8))),
                  metadata={"kitaru.tool_definitions": tools, "retries": retries})
        return msg, usage, lat, retries

    def tool(self, env_run):
        def run(name, args):
            start = datetime.now(UTC)
            out = env_run(name, args)
            failed = out.startswith("Error")
            self._add(node_type=NodeType.TOOL_CALL, name=name, tool_name=name, inputs=args, outputs=out,
                      status=NodeStatus.FAILED if failed else NodeStatus.COMPLETED, error=out[:500] if failed else None,
                      started_at=start, ended_at=datetime.now(UTC))
            return out
        return run

    def underwriter(self, task, transcript):
        start = datetime.now(UTC)
        reply, cost = H.M_underwriter_reply(task, transcript)
        self._add(node_type=NodeType.SPAN, name="underwriter", status=NodeStatus.COMPLETED, started_at=start,
                  ended_at=datetime.now(UTC), inputs={"copilot": transcript[-1][1]}, outputs={"reply": reply},
                  metadata={"simulated": True, "simulator": H.SIMULATOR, "cost_usd": round(cost, 6)})
        return reply, cost


H.M_call_model, H.M_underwriter_reply = H.call_model, H.underwriter_reply
H.grade = lambda *a: (None, "graded by the Kitaru evaluator", 0.0)  # grading belongs to the evaluator


def episode(task_id, key):
    rec = Recorder(DEFAULT_MODEL, key)
    H.call_model, H.underwriter_reply = rec.call_model, rec.underwriter
    env = H.Env()
    env.run = rec.tool(env.run)
    row, transcript = H.run_task(env, key, TASKS[task_id])
    return rec, row, transcript


async def record(client, task_id, key, origin, agent_id, session_name=None):
    task = TASKS[task_id]
    started = datetime.now(UTC)
    session = await client.sessions.create(SessionCreateRequest(
        agent_id=agent_id, origin=origin, status=SessionStatus.IN_PROGRESS, name=session_name or task_id,
        inputs={"task_id": task_id, "request": H.SEEDS[task["task"]]}, outputs=None, started_at=started,
        metadata={"task_type": task["task"], "expected": task["reference"], "model_key": key},
        framework=FRAMEWORK, adapter_version=ADAPTER_VERSION))
    rec, row, transcript = await asyncio.to_thread(episode, task_id, key)
    root = SessionNodeCreateRequest(external_id="root", node_type=NodeType.SPAN, name="underwriting-case",
                                    status=NodeStatus.COMPLETED, started_at=started, ended_at=datetime.now(UTC),
                                    inputs={"task_id": task_id}, outputs={"status": row["status"]}, attributes={})
    await client.sessions.ingest_nodes(session.id, SessionNodeBatchRequest(nodes=[root, *rec.nodes]))
    ok = row["status"] == "finished"
    await client.sessions.update(session.id, SessionUpdateRequest(
        status=SessionStatus.COMPLETED if ok else SessionStatus.FAILED,
        outputs={"final_answer": row["final_answer"], "status": row["status"], "failures": row["failures"],
                 "transcript": transcript["transcript"] if transcript else None,
                 "underwriter_cost_usd": round(row["sim_cost"], 6)},
        error=None if ok else row["status"], ended_at=datetime.now(UTC)))
    return session.id, row


async def run_task():
    inputs = get_task_inputs() or {}
    if get_task_id() is None:
        raise RuntimeError("No task id in the environment")
    agent_id = uuid.UUID(os.environ["UW_AGENT_ID"])
    replay_id = os.environ.get("KITARU_REPLAY_ID")
    key, origin = DEFAULT_MODEL, SessionOrigin.RECORDED
    async with KitaruAPIClient() as client:
        if replay_id:
            replay = await client.replays.get(uuid.UUID(replay_id))
            policies = [replay.tool_policy.default, *replay.tool_policy.tools.values()]
            if not all(isinstance(p, PassthroughConfig) for p in policies):
                raise RuntimeError("This agent supports only the passthrough tool policy (read-only fixed database)")
            o = replay.override
            if o is not None and o.model is not None:
                key = o.model if isinstance(o.model, str) else o.model.get(key, key)
            if key not in H.M.MODELS:
                raise RuntimeError(f"Unknown model key {key!r}")
            origin = SessionOrigin.REPLAY
        sid, row = await record(client, inputs["task_id"], key, origin, agent_id,
                                os.environ.get("KITARU_SESSION_NAME"))
        print(f"Recorded session {sid} task={inputs['task_id']} model={key} status={row['status']}")


async def record_directly(ids, key, agent_id):
    async with KitaruAPIClient() as client:
        sem = asyncio.Semaphore(8)

        async def one(t):
            async with sem:
                sid, row = await record(client, t, key, SessionOrigin.RECORDED, agent_id)
                print(f"{t} {row['status']} session={sid}", flush=True)
        await asyncio.gather(*(one(t) for t in ids))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--record", default=None)
    ap.add_argument("--model", default=DEFAULT_MODEL)
    a = ap.parse_args()
    if a.record:
        # The recorder swaps module-level hooks per episode, so record one case at a time per process.
        for t in a.record.split(","):
            asyncio.run(record_directly([t], a.model, uuid.UUID(os.environ["UW_AGENT_ID"])))
    else:
        asyncio.run(run_task())


if __name__ == "__main__":
    main()
