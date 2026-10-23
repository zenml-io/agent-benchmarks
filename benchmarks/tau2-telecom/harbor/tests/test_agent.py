"""End-to-end check of the Harbor agent's in-sandbox runner, offline and without any model.

    TAU2_BENCH_ROOT=/path/to/tau2-bench uv run --extra harbor-dev pytest harbor/tests/test_agent.py

The task's real MCP sidecar (`environment/runtime-server/server.py`, tau2's Telecom environment) runs
in memory with tau2's user simulator swapped for a scripted customer. A scripted PydanticAI model plays
the reference solution through the runner's tools: account actions as tool calls, device actions as
messages asking the customer, who performs them. Then the task's own grader scores the conversation the
sidecar recorded, and the Kitaru recording the local sink captured is checked.
"""

import argparse
import asyncio
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

sys.dont_write_bytecode = True  # the tests import task files; keep __pycache__ out of the task folders

HARBOR = Path(__file__).resolve().parents[1]
TAU2_ROOT = os.environ.get("TAU2_BENCH_ROOT")
pytestmark = pytest.mark.skipif(not TAU2_ROOT, reason="set TAU2_BENCH_ROOT to a tau2-bench checkout")
sys.path.insert(0, str(HARBOR / "agent" / "tau2_kitaru_harbor"))

# Two kinds of task: device fixes plus an account fix (35), and device fixes only (36).
TASKS = ["telecom-test-35", "telecom-test-36"]


def load_server(task: Path, tmp: Path) -> Any:
    """Import the task's sidecar with a scripted customer in place of tau2's LLM user simulator."""
    import tau2.user.user_simulator as user_module
    from tau2.data_model.message import ToolCall, ToolMessage, UserMessage

    class ScriptedCustomer(user_module.UserSimulator):
        def _generate_next_message(self, message: Any, state: Any) -> UserMessage:
            if isinstance(message, ToolMessage):
                return UserMessage(role="user", content="Done, I did that on my phone.")
            text = message.content or ""
            if text.startswith("Please run "):
                name, args = text.removeprefix("Please run ").split(" ", 1)
                return UserMessage(role="user", content=None, tool_calls=[
                    ToolCall(id=f"user_{len(state.messages)}", name=name, arguments=json.loads(args), requestor="user")])
            if "Is everything working" in text:
                return UserMessage(role="user", content="Yes, all good. Thanks! ###STOP###")
            if "How can I help" in text:
                return UserMessage(role="user", content="Hi, my phone has a problem.")
            return UserMessage(role="user", content="OK.")

    user_module.UserSimulator = ScriptedCustomer
    source = (task / "environment" / "runtime-server" / "server.py").read_text()
    source = source.replace('Path("/opt/tau2-bench")', f"Path({TAU2_ROOT!r})")
    source = source.replace('Path("/app/task_config.json")', f"Path({str(task / 'environment/runtime-server/task_config.json')!r})")
    path = tmp / "server_under_test.py"
    path.write_text(source)
    spec = importlib.util.spec_from_file_location(f"server_{task.name.replace('-', '_')}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def scripted_model(oracle: dict[str, Any]) -> Any:
    from pydantic_ai.messages import ModelResponse, TextPart, ToolCallPart
    from pydantic_ai.models.function import FunctionModel

    steps: list[Any] = []
    for action in oracle["actions"]:
        if action.get("requestor") == "user":
            content = f"Please run {action['name']} {json.dumps(action.get('arguments') or {})}"
            steps.append(ToolCallPart("send_message_to_user", {"content": content}))
        else:
            steps.append(ToolCallPart(action["name"], action.get("arguments") or {}))
    steps.append(ToolCallPart("send_message_to_user", {"content": "Is everything working now?"}))
    steps.append(TextPart("DONE"))

    def respond(messages: list[Any], info: Any) -> ModelResponse:
        done = sum(isinstance(m, ModelResponse) for m in messages)
        return ModelResponse(parts=[steps[min(done, len(steps) - 1)]])

    return FunctionModel(respond)


def args(tmp: Path, task: Path, **extra: Any) -> argparse.Namespace:
    fields = {"instruction_file": str(task / "instruction.md"), "addendum_file": None, "model": "scripted",
              "dry_run": False, "case": task.name[-2:], "arm": "test", "record_dir": str(tmp / "kitaru")}
    return argparse.Namespace(**(fields | extra))


def grade(task: Path, state: Path, tmp: Path) -> float:
    reward = tmp / "reward.txt"
    subprocess.run([sys.executable, str(task / "tests" / "evaluate.py"), "--config", str(task / "tests" / "config.json"),
                    "--runtime-log", str(state), "--reward", str(reward), "--result", str(tmp / "result.json")],
                   check=True, capture_output=True)
    return float(reward.read_text())


@pytest.mark.parametrize("name", TASKS)
def test_scripted_reference_through_runner_scores_1_and_is_recorded(name: str, tmp_path: Path, monkeypatch) -> None:
    import runner
    from kitaru_sink import KitaruSink

    task = HARBOR / "tasks" / name
    state = tmp_path / "tau3_runtime_state.json"
    monkeypatch.setenv("TAU3_RUNTIME_STATE_PATH", str(state))
    monkeypatch.setenv("KITARU_API_TOKEN", "test")
    monkeypatch.setenv("KITARU_DISABLE_CLIENT_ANALYTICS", "1")
    server = load_server(task, tmp_path)
    oracle = json.loads((task / "solution" / "oracle.json").read_text())

    with KitaruSink(tmp_path / "kitaru") as sink:
        monkeypatch.setenv("KITARU_API_URL", sink.url)
        summary = asyncio.run(runner.run_episode(args(tmp_path, task), mcp_target=server.mcp,
                                                 model=scripted_model(oracle)))

    assert summary["run_error"] is None
    assert summary["runtime"]["termination_reason"] == "user_stop"
    assert summary["agent_tool_schemas"] == 13
    assert grade(task, state, tmp_path) == 1.0

    sessions = json.loads((tmp_path / "kitaru" / "session.json").read_text())
    assert len(sessions) == 1
    session, nodes = sessions[0]["session"], sessions[0]["nodes"]
    assert session["status"] == "completed" and session["name"] == f"tau2 telecom case {name[-2:]} test"
    assert sum(n["node_type"] == "llm_call" for n in nodes) == len(oracle["actions"]) + 2
    tool_nodes = [n["name"] for n in nodes if n["node_type"] == "tool_call"]
    assert tool_nodes.count("send_message_to_user") == sum(a.get("requestor") == "user" for a in oracle["actions"]) + 1
    requests = [json.loads(line) for line in (tmp_path / "kitaru" / "requests.jsonl").read_text().splitlines()]
    assert requests[0]["method"] == "POST" and requests[0]["path"] == "/api/v1/sessions"
    assert requests[-1]["method"] == "PATCH" and requests[-1]["body"]["status"] == "completed"

    # upload_recordings.py resends the recording unchanged; a second sink stands in for the server.
    sys.path.insert(0, str(HARBOR / "scripts"))
    import upload_recordings
    from kitaru.client import KitaruAPIClient

    async def upload(url: str) -> list[str]:
        client = KitaruAPIClient(base_url=url, api_key="test")
        try:
            return await upload_recordings.upload_trial(client, requests, "11111111-1111-1111-1111-111111111111", None,
                                                        {"reward": 1.0, "graded_by": "harbor verifier"})
        finally:
            await client.close()

    with KitaruSink(tmp_path / "server") as server_sink:
        assert len(asyncio.run(upload(server_sink.url))) == 1
    uploaded = json.loads((tmp_path / "server" / "session.json").read_text())[0]
    assert uploaded["session"]["agent_id"] == "11111111-1111-1111-1111-111111111111"
    # The verifier's grade rides on the final outputs, next to the recorded answer.
    recorded_outputs = json.loads(sessions[0]["session"]["outputs"])
    assert json.loads(uploaded["session"]["outputs"]) == recorded_outputs | {"tau2": {"reward": 1.0,
                                                                                      "graded_by": "harbor verifier"}}
    assert {n["external_id"]: n["status"] for n in uploaded["nodes"]} == {n["external_id"]: n["status"] for n in nodes}


def test_dry_run_records_without_starting_the_conversation(tmp_path: Path, monkeypatch) -> None:
    import runner
    from kitaru_sink import KitaruSink

    task = HARBOR / "tasks" / TASKS[0]
    state = tmp_path / "tau3_runtime_state.json"
    monkeypatch.setenv("TAU3_RUNTIME_STATE_PATH", str(state))
    monkeypatch.setenv("KITARU_API_TOKEN", "test")
    server = load_server(task, tmp_path)
    with KitaruSink(tmp_path / "kitaru") as sink:
        monkeypatch.setenv("KITARU_API_URL", sink.url)
        summary = asyncio.run(runner.run_episode(args(tmp_path, task, dry_run=True), mcp_target=server.mcp))
    assert summary["run_error"] is None and summary["runtime"]["termination_reason"] is None
    assert json.loads(state.read_text())["start_tool_called"] is False
    assert grade(task, state, tmp_path) == 0.0
    assert json.loads((tmp_path / "kitaru" / "session.json").read_text())[0]["session"]["status"] == "completed"


def test_policy_given_to_the_model_is_tau2s() -> None:
    """The runner takes the policy from the task instruction; it must equal what the original agent used."""
    import runner
    from tau2.registry import registry
    from tau2.runner.build import agent_domain_policy

    expected = agent_domain_policy(registry.get_env_constructor("telecom")())
    for task in sorted((HARBOR / "tasks").glob("telecom-test-*")):
        assert runner.extract_policy((task / "instruction.md").read_text()) == expected, task.name
