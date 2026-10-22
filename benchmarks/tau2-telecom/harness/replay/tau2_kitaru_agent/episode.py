"""One tau2-bench Telecom episode with a PydanticAI agent recorded and replayed through Kitaru.

tau2's own Orchestrator runs the episode (environment, user simulator, step limit) in a
background thread. The agent side is one PydanticAI run: every tau2 agent tool is a
PydanticAI tool, and the agent talks to the customer only through send_message_to_user.
A bridge turns each tool call into the tau2 AssistantMessage the orchestrator expects
and hands back the environment's or the user's reply, so the whole conversation is one
KitaruAgent run (one Kitaru session) and tau2 grades the native trajectory afterwards.
"""

import asyncio
import json
import os
import queue
import threading
import uuid
from collections.abc import Callable
from typing import Any

from kitaru.task import get_task_inputs
from kitaru_pydantic_ai import KitaruAgent
from pydantic_ai import Agent, ModelRetry, Tool, UsageLimits
from tau2.agent.base_agent import HalfDuplexAgent
from tau2.data_model.message import AssistantMessage, MultiToolMessage, ToolCall, ToolMessage, UserMessage
from tau2.data_model.semantic_communication import CommunicateScorer, CommunicateScoring
from tau2.evaluator.evaluator import EvaluationType, evaluate_simulation
from tau2.orchestrator.orchestrator import Orchestrator
from tau2.registry import registry
from tau2.runner.build import agent_domain_policy, user_tools_for_task
from tau2.user.user_simulator import UserSimulator

DOMAIN = "telecom"
SPLIT = "test"
AGENT_MODEL = os.environ.get("TAU2_AGENT_MODEL", "openai:gpt-5.2-2025-12-11")
USER_MODEL = "gpt-4.1-2025-04-14"  # tau2's default user simulator
MAX_STEPS = 100  # tau2's default
STOP = "###STOP###"
_DONE = object()

AGENT_INSTRUCTION = (
    "You are a customer service agent that helps the user according to the <policy> provided below.\n"
    "In each turn you can either:\n"
    "- Send a message to the user with the send_message_to_user tool (its result is the user's reply).\n"
    "- Make a tool call.\n"
    "You cannot do both at the same time.\n\n"
    "Try to be helpful and always follow the policy."
)


def load_task(case: int):
    """Return the tau2 task for an opaque case number (its index in the test split)."""
    tasks = registry.get_tasks_loader(DOMAIN)(SPLIT)
    return tasks[case]


class Bridge(HalfDuplexAgent):
    """tau2 agent whose messages come from the PydanticAI run, one exchange at a time."""

    def __init__(self) -> None:
        self.to_agent: queue.Queue = queue.Queue()
        self.from_agent: queue.Queue = queue.Queue()
        self.done = threading.Event()

    def get_init_state(self, message_history=None):
        return None

    def generate_next_message(self, message, state):
        self.to_agent.put(message)
        return self.from_agent.get(), state

    def is_stop(self, message) -> bool:
        return bool(message.content) and STOP in message.content

    def stop(self, message=None, state=None) -> None:
        return None

    def set_seed(self, seed: int) -> None:
        return None

    def exchange(self, message: AssistantMessage) -> Any:
        """Send one agent message and wait for whatever the orchestrator routes back."""
        if self.done.is_set():
            return _DONE
        self.from_agent.put(message)
        return self.to_agent.get()


def _content(message: Any) -> str:
    if isinstance(message, MultiToolMessage):
        return "\n".join(m.content or "" for m in message.tool_messages)
    return message.content or ""


def build_agent(bridge: Bridge, environment, first_user_message: str, model: str,
                finish: Callable[[], dict[str, Any]]) -> Agent[None, str]:
    """PydanticAI agent with tau2's agent tools plus send_message_to_user."""
    lock = threading.Lock()
    policy = agent_domain_policy(environment)
    # An agent version can append general instructions (the prompt-audit arm); unset means none.
    addendum = os.environ.get("TAU2_INSTRUCTION_ADDENDUM", "")
    agent_instruction = f"{AGENT_INSTRUCTION}\n{addendum}" if addendum else AGENT_INSTRUCTION
    instructions = (
        f"<instructions>\n{agent_instruction}\n</instructions>\n<policy>\n{policy}\n</policy>\n\n"
        f"The conversation so far:\nYou: Hi! How can I help you today?\nUser: {first_user_message}"
    )

    def send_message_to_user(content: str) -> str:
        """Send a message to the user and return the user's reply."""
        with lock:
            reply = bridge.exchange(AssistantMessage(role="assistant", content=content))
        if reply is _DONE:
            return "The user has left; the conversation is over. Reply with the single word DONE."
        return _content(reply)

    tools = [Tool(send_message_to_user, takes_ctx=False)]
    for tau2_tool in environment.get_tools():
        schema = tau2_tool.openai_schema["function"]

        def call(_name=schema["name"], **arguments: Any) -> str:
            with lock:
                result = bridge.exchange(AssistantMessage(role="assistant", tool_calls=[
                    ToolCall(id=f"call_{uuid.uuid4().hex[:24]}", name=_name, arguments=arguments, requestor="assistant")]))
            if result is _DONE:
                return "The conversation is over. Reply with the single word DONE."
            return _content(result)

        tools.append(Tool.from_schema(call, name=schema["name"], description=schema.get("description", ""),
                                      json_schema=schema["parameters"], takes_ctx=False))

    agent = Agent[None, str](model, instructions=instructions, tools=tools, retries=30)

    @agent.output_validator
    def deliver_text(output: str) -> str:
        # A plain-text answer before the user has left is a message to the user, as in tau2.
        if not bridge.done.is_set():
            with lock:
                reply = bridge.exchange(AssistantMessage(role="assistant", content=output))
            if reply is not _DONE:
                raise ModelRetry(f"The user replied: {_content(reply)}")
        # The episode is over: the run's output is tau2's graded result, written before the
        # session closes (a completed Kitaru session accepts no updates). The model never sees it.
        return json.dumps(finish() | {"answer": output})

    return agent


async def run_episode(case: int, model: str = AGENT_MODEL) -> dict[str, Any]:
    task = load_task(case)
    environment = registry.get_env_constructor(DOMAIN)()
    user = UserSimulator(llm=USER_MODEL, instructions=str(task.user_scenario),
                         tools=user_tools_for_task(environment, task))
    bridge = Bridge()
    orchestrator = Orchestrator(domain=DOMAIN, agent=bridge, user=user, environment=environment,
                                task=task, max_steps=MAX_STEPS)
    outcome: dict[str, Any] = {}

    def orchestrate() -> None:
        try:
            outcome["simulation"] = orchestrator.run()
        except BaseException as exc:  # noqa: BLE001
            outcome["error"] = repr(exc)
        finally:
            bridge.done.set()
            bridge.to_agent.put(_DONE)

    thread = threading.Thread(target=orchestrate, daemon=True)
    graded: dict[str, Any] = {}

    def finish() -> dict[str, Any]:
        """Wait for tau2 to end the episode and grade it once."""
        if not graded:
            thread.join(600)
            sim = outcome.get("simulation")
            reward = None
            if sim is not None:
                info = evaluate_simulation(sim, task, EvaluationType.ALL, solo_mode=False, domain=DOMAIN,
                                           communicate_scoring=CommunicateScoring(scorer=CommunicateScorer.SUBSTRING))
                reward = info.reward
            graded.update({
                "case": case, "orchestrator_error": outcome.get("error"),
                "tau2": {"task_id": task.id, "split": SPLIT, "reward": reward,
                         "termination_reason": getattr(sim, "termination_reason", None),
                         "user_cost_usd": getattr(sim, "user_cost", None),
                         "messages": len(sim.messages) if sim is not None else None,
                         "user_model": USER_MODEL, "max_steps": MAX_STEPS}})
        return graded

    thread.start()
    first = await asyncio.to_thread(bridge.to_agent.get)
    run_error = None
    if first is not _DONE:
        version = os.environ.get("TAU2_AGENT_VERSION_ID")
        agent = KitaruAgent(build_agent(bridge, environment, _content(first), model, finish),
                            agent_version_id=uuid.UUID(version) if version else None,
                            session_name=session_name(case))
        try:
            await agent.run(f"Case {case}: continue the conversation with the user above.",
                            usage_limits=UsageLimits(request_limit=MAX_STEPS))
        except Exception as exc:  # noqa: BLE001
            run_error = repr(exc)
        if not bridge.done.is_set():
            bridge.from_agent.put(AssistantMessage(role="assistant", content=STOP))
    return await asyncio.to_thread(finish) | {"run_error": run_error}


def session_name(case: int) -> str:
    return f"tau2 telecom case {case} {os.environ.get('TAU2_RUN_TAG', '')}".strip()


async def main() -> None:
    inputs = get_task_inputs()
    text = inputs if isinstance(inputs, str) else json.dumps(inputs)
    case = int(text.split("Case ", 1)[1].split(":", 1)[0]) if "Case " in text else int(os.environ["TAU2_CASE"])
    print(json.dumps(await run_episode(case)))


if __name__ == "__main__":
    asyncio.run(main())
