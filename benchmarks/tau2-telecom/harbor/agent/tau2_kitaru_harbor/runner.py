"""The original tau2 Telecom PydanticAI agent, run inside a Harbor trial against the task's MCP sidecar.

    python runner.py --mcp-url http://tau3-runtime:8000/mcp --model openai:gpt-5.2-2025-12-11 \
        --instruction-file /tmp/instruction.md --case 5 --arm baseline --record-dir /logs/agent/kitaru

Same agent as `harness/replay/tau2_kitaru_agent/episode.py`: the same instructions (tau2's Telecom policy,
plus the optional prompt-audit rule), the same tools (tau2's 13 agent tools with tau2's own schemas, plus
`send_message_to_user`, whose result is the customer's reply), the same output validator (plain text
before the customer leaves is a message to the customer), the same limits (100 model requests,
30 output retries), wrapped in Kitaru's `KitaruAgent` so one episode is one Kitaru session.

What changed is where the conversation lives. In the original, tau2's Orchestrator ran in a thread and a
bridge handed messages across. Here the task's `tau3-runtime` MCP sidecar holds tau2's environment and
user simulator: every tool call and every message to the customer is one MCP call, and the sidecar
records the conversation the verifier grades. The model sees only the tools above; the sidecar's
control tools (configure_run, record_termination, submit_assistant_tool_calls, ...) are not offered.

Kitaru records to a local sink (kitaru_sink.py) whose files land in the trial's agent logs.
Models: `openai:<id>` and `openai-responses:<id>` go to OpenAI; `provider-a:<id>` goes to an
OpenAI-compatible provider through harness/replay/model_router.py, started here on 127.0.0.1.
"""

import argparse
import asyncio
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from fastmcp import Client
from pydantic_ai import Agent, ModelRetry, Tool, UsageLimits

AGENT_INSTRUCTION = (
    "You are a customer service agent that helps the user according to the <policy> provided below.\n"
    "In each turn you can either:\n"
    "- Send a message to the user with the send_message_to_user tool (its result is the user's reply).\n"
    "- Make a tool call.\n"
    "You cannot do both at the same time.\n\n"
    "Try to be helpful and always follow the policy."
)
GREETING = "Hi! How can I help you today?"  # tau2's DEFAULT_FIRST_AGENT_MESSAGE, sent by the sidecar
MAX_STEPS = 100
OUTPUT_RETRIES = 30
STOP = "###STOP###"
USER_LEFT = "The user has left; the conversation is over. Reply with the single word DONE."
CONVERSATION_OVER = "The conversation is over. Reply with the single word DONE."
ROUTER_PORT = 8766


def extract_policy(instruction: str) -> str:
    """The text between the last <policy> tags of the task instruction (tau2's composed Telecom policy)."""
    found = re.findall(r"<policy>\n(.*)\n</policy>", instruction, flags=re.DOTALL)
    if not found:
        raise SystemExit("instruction has no <policy> block")
    return found[-1]


def text_of(result: Any) -> str:
    return "\n".join(getattr(block, "text", "") or "" for block in result.content)


class Runtime:
    """Serialized access to the tau3-runtime MCP tools, tracking whether the conversation ended."""

    def __init__(self, client: Client) -> None:
        self.client = client
        self.lock = asyncio.Lock()
        self.done = False
        self.tools_called: list[str] = []

    async def call(self, name: str, arguments: dict[str, Any]) -> tuple[str, bool]:
        result = await self.client.call_tool(name, arguments, raise_on_error=False, timeout=600)
        return text_of(result), bool(result.is_error)

    async def status(self) -> dict[str, Any]:
        text, _ = await self.call("get_runtime_status", {})
        return json.loads(text)

    async def message_user(self, content: str) -> str:
        """Send one agent message; returns the customer's reply, or USER_LEFT once the conversation ended."""
        async with self.lock:
            if self.done:
                return USER_LEFT
            text, error = await self.call("submit_assistant_message", {"message": content})
            if error:
                self.done = (await self.status()).get("termination_reason") is not None
                return USER_LEFT if self.done else text
            reply = json.loads(text)
            if reply.get("termination_reason") is not None:
                self.done = True
                return USER_LEFT
            return reply.get("observation") or ""

    async def domain_tool(self, name: str, arguments: dict[str, Any]) -> str:
        async with self.lock:
            if self.done:
                return CONVERSATION_OVER
            self.tools_called.append(name)
            text, error = await self.call(name, arguments)
            if (await self.status()).get("termination_reason") is not None:
                self.done = True
                if error:
                    return CONVERSATION_OVER
            return text


def build_agent(runtime: Runtime, schemas: list[dict[str, Any]], policy: str, first_user_message: str,
                model: Any, addendum: str) -> Agent[None, str]:
    agent_instruction = f"{AGENT_INSTRUCTION}\n{addendum}" if addendum else AGENT_INSTRUCTION
    instructions = (
        f"<instructions>\n{agent_instruction}\n</instructions>\n<policy>\n{policy}\n</policy>\n\n"
        f"The conversation so far:\nYou: {GREETING}\nUser: {first_user_message}"
    )

    async def send_message_to_user(content: str) -> str:
        """Send a message to the user and return the user's reply."""
        runtime.tools_called.append("send_message_to_user")
        return await runtime.message_user(content)

    tools = [Tool(send_message_to_user, takes_ctx=False)]
    for schema in schemas:
        function = schema["function"]

        async def call(_name: str = function["name"], **arguments: Any) -> str:
            return await runtime.domain_tool(_name, arguments)

        tools.append(Tool.from_schema(call, name=function["name"], description=function.get("description", ""),
                                      json_schema=function["parameters"], takes_ctx=False))

    agent = Agent[None, str](model, instructions=instructions, tools=tools, retries=OUTPUT_RETRIES)

    @agent.output_validator
    async def deliver_text(output: str) -> str:
        # A plain-text answer before the user has left is a message to the user, as in tau2.
        if not runtime.done:
            reply = await runtime.message_user(output)
            if reply != USER_LEFT:
                raise ModelRetry(f"The user replied: {reply}")
        return json.dumps({"answer": output})

    return agent


def resolve_model(name: str, dry_run: bool) -> tuple[Any, subprocess.Popen | None]:
    if dry_run:
        from pydantic_ai.models.test import TestModel

        return TestModel(call_tools=[], custom_output_text="DONE"), None
    if not name.startswith("provider-a:"):
        return name, None
    router = subprocess.Popen([sys.executable, str(Path(__file__).with_name("model_router.py")),
                               "--port", str(ROUTER_PORT)])
    os.environ["OPENAI_BASE_URL"] = f"http://127.0.0.1:{ROUTER_PORT}/v1"
    time.sleep(1.0)
    return "openai:" + name.removeprefix("provider-a:"), router


async def run_episode(a: argparse.Namespace, mcp_target: Any = None, model: Any = None) -> dict[str, Any]:
    """One episode. Tests pass an in-memory MCP server as `mcp_target` and a scripted PydanticAI model."""
    from kitaru_pydantic_ai import KitaruAgent

    policy = extract_policy(Path(a.instruction_file).read_text())
    addendum = Path(a.addendum_file).read_text().strip() if a.addendum_file else ""
    model, router = (model, None) if model is not None else resolve_model(a.model, a.dry_run)
    summary: dict[str, Any] = {"arm": a.arm, "model": a.model, "case": a.case, "dry_run": a.dry_run,
                               "prompt_rule": bool(addendum), "run_error": None}
    try:
        async with Client(mcp_target or a.mcp_url, timeout=600) as client:
            runtime = Runtime(client)
            schemas_text, _ = await runtime.call("get_assistant_tool_schemas", {})
            schemas = json.loads(schemas_text)
            if a.dry_run:
                first, runtime.done = "(dry run: the conversation was not started)", True
            else:
                first, error = await runtime.call("start_conversation", {})
                if error:
                    raise RuntimeError(f"start_conversation failed: {first}")
            agent = KitaruAgent(build_agent(runtime, schemas, policy, first, model, addendum),
                                session_name=f"tau2 telecom case {a.case} {a.arm}".strip())
            try:
                result = await agent.run(f"Case {a.case}: continue the conversation with the user above.",
                                         usage_limits=UsageLimits(request_limit=MAX_STEPS))
                usage = result.usage
                summary |= {"input_tokens": usage.input_tokens, "output_tokens": usage.output_tokens,
                            "cache_read_tokens": usage.cache_read_tokens, "requests": usage.requests}
            except Exception as exc:  # noqa: BLE001
                summary["run_error"] = repr(exc)
            if not runtime.done:
                # The original sent tau2 a stop message when the agent run ended without the user leaving.
                await runtime.call("end_conversation", {"message": STOP})
            summary |= {"runtime": await runtime.status(), "tools_called": runtime.tools_called,
                        "agent_tool_schemas": len(schemas)}
    finally:
        if router is not None:
            router.terminate()
    return summary


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mcp-url", required=True)
    ap.add_argument("--model", required=True)
    ap.add_argument("--instruction-file", required=True)
    ap.add_argument("--case", default="")
    ap.add_argument("--arm", default="")
    ap.add_argument("--addendum-file")
    ap.add_argument("--record-dir", required=True)
    ap.add_argument("--summary", required=True)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    from kitaru_sink import KitaruSink

    # Kitaru's client reads these when the run starts; nothing leaves the sandbox.
    os.environ.update(KITARU_API_TOKEN="local-recording-sink", KITARU_DISABLE_CLIENT_ANALYTICS="1", DO_NOT_TRACK="1")
    with KitaruSink(Path(a.record_dir)) as sink:
        os.environ["KITARU_API_URL"] = sink.url
        summary = asyncio.run(run_episode(a))
    sessions = json.loads((Path(a.record_dir) / "session.json").read_text())
    costs = [n.get("cost") for s in sessions for n in s["nodes"] if n.get("node_type") == "llm_call"]
    summary["kitaru_sessions"] = len(sessions)
    summary["agent_cost_usd"] = sum(float(c) for c in costs if c is not None) if any(costs) else None
    Path(a.summary).write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary))


if __name__ == "__main__":
    main()
