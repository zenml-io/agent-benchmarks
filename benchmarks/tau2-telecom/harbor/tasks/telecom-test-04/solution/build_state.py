"""Write a tau3-runtime state file for this task without a model: the reference solution and the checks.

    python3 /solution/build_state.py <mode>

Modes (each writes the file the verifier grades, /logs/agent/tau3_runtime_state.json, or
$TAU3_RUNTIME_STATE_PATH):

- reference: every expected action in order, each executed against tau2's Telecom environment for
  its real result, then the expected information as agent messages; ends with agent_stop. This is the
  reference logic of Harbor's tau3-bench adapter (adapters/tau3-bench, solution/solve.sh, Apache-2.0),
  moved into a script so the checks below can share it.
- rechecks (alternative valid solution): a conversation instead of a bare action list. The agent looks
  the customer up by phone, the user re-checks the status bar after each device change, both sides talk
  between steps, and the user ends the call (user_stop). Same state changes, different path.
- do_nothing (shortcut): the agent says the issue is resolved and stops.
- transfer_now (shortcut): the agent transfers to a human agent at once.
- account_side_only (shortcut): only the agent's account-side actions; the device fixes the user must
  make are skipped.

oracle.json holds the expected actions and the task's initial state; it sits next to this script.
"""

import json
import os
import sys
from pathlib import Path
from typing import Any

ORACLE = Path(__file__).with_name("oracle.json")
STATE_PATH = Path(os.environ.get("TAU3_RUNTIME_STATE_PATH", "/logs/agent/tau3_runtime_state.json"))
TAU2_ROOT = Path(os.environ.get("TAU2_BENCH_ROOT", "/opt/tau2-bench"))
if (TAU2_ROOT / "src" / "tau2").exists():
    sys.path.insert(0, str(TAU2_ROOT / "src"))
    os.environ.setdefault("TAU2_DATA_DIR", str(TAU2_ROOT / "data"))

from tau2.data_model.message import AssistantMessage, ToolCall, UserMessage  # noqa: E402
from tau2.data_model.tasks import EnvFunctionCall, InitializationData  # noqa: E402
from tau2.domains.telecom.environment import get_environment_manual_policy  # noqa: E402

GREETING = "Hi! How can I help you today?"
TRANSFER_LINE = "YOU ARE BEING TRANSFERRED TO A HUMAN AGENT. PLEASE HOLD ON."


class Conversation:
    """Messages plus the Telecom environment their tool calls run against."""

    def __init__(self, oracle: dict[str, Any]) -> None:
        self.environment = get_environment_manual_policy(solo_mode=False)
        raw_data = oracle.get("initialization_data")
        actions = [EnvFunctionCall(**a) for a in oracle.get("initialization_actions") or []]
        self.environment.set_state(
            initialization_data=InitializationData.model_validate(raw_data) if raw_data is not None else None,
            initialization_actions=actions or None,
            message_history=[],
        )
        self.messages: list[Any] = []
        self.calls = 0

    def say(self, role: str, content: str) -> None:
        cls = UserMessage if role == "user" else AssistantMessage
        self.messages.append(cls(role=role, content=content))

    def call(self, requestor: str, name: str, arguments: dict[str, Any]) -> Any:
        tool_call = ToolCall(id=f"oracle_{self.calls}", name=name, arguments=arguments, requestor=requestor)
        self.calls += 1
        cls = UserMessage if requestor == "user" else AssistantMessage
        self.messages.append(cls(role=requestor, content=None, tool_calls=[tool_call]))
        result = self.environment.get_response(tool_call)
        self.messages.append(result)
        return result

    def write(self, oracle: dict[str, Any], termination_reason: str) -> None:
        STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        STATE_PATH.write_text(json.dumps({
            "domain": oracle["domain"],
            "task_id": oracle["task_id"],
            "termination_reason": termination_reason,
            "bootstrap_complete": True,
            "start_tool_called": True,
            "messages": [m.model_dump(mode="json") for m in self.messages],
        }, indent=2), encoding="utf-8")


def user_phone(oracle: dict[str, Any]) -> str | None:
    for action in oracle.get("initialization_actions") or []:
        if action.get("func_name") == "set_user_info":
            return action.get("arguments", {}).get("phone_number")
    return None


def build(mode: str, oracle: dict[str, Any]) -> None:
    conv = Conversation(oracle)
    actions = oracle.get("actions") or []
    communicate = oracle.get("communicate_info") or []

    if mode == "reference":
        for a in actions:
            conv.call(a.get("requestor", "assistant"), a["name"], a.get("arguments") or {})
        for info in communicate:
            conv.say("assistant", info)
        conv.write(oracle, "agent_stop")
    elif mode == "rechecks":
        conv.say("assistant", GREETING)
        conv.say("user", "Hi, my phone isn't working the way it should. Can you help?")
        phone = user_phone(oracle)
        if phone:
            conv.call("assistant", "get_customer_by_phone", {"phone_number": phone})
        conv.say("assistant", "Thanks, I found your account. Let's work through this step by step.")
        for a in actions:
            requestor = a.get("requestor", "assistant")
            if requestor == "user":
                conv.say("assistant", f"Please do this on your phone: {a['name'].replace('_', ' ')}.")
            conv.call(requestor, a["name"], a.get("arguments") or {})
            if requestor == "user":
                conv.call("user", "check_status_bar", {})
                conv.say("user", "Done. I checked the status bar again.")
        for info in communicate:
            conv.say("assistant", info)
        conv.say("assistant", "Is everything working now?")
        conv.say("user", "Yes, thank you! ###STOP###")
        conv.write(oracle, "user_stop")
    elif mode == "do_nothing":
        conv.say("assistant", GREETING)
        conv.say("user", "My phone has a problem.")
        conv.say("assistant", "Your issue has been resolved. Have a nice day!")
        conv.write(oracle, "agent_stop")
    elif mode == "transfer_now":
        conv.say("assistant", GREETING)
        conv.say("user", "My phone has a problem.")
        conv.call("assistant", "transfer_to_human_agents", {"summary": "Customer reports a phone problem."})
        conv.say("assistant", TRANSFER_LINE)
        conv.write(oracle, "agent_stop")
    elif mode == "account_side_only":
        for a in actions:
            if a.get("requestor", "assistant") != "user":
                conv.call("assistant", a["name"], a.get("arguments") or {})
        for info in communicate:
            conv.say("assistant", info)
        conv.write(oracle, "agent_stop")
    else:
        raise SystemExit(f"unknown mode {mode!r}")


if __name__ == "__main__":
    build(sys.argv[1] if len(sys.argv) > 1 else "reference", json.loads(ORACLE.read_text(encoding="utf-8")))
