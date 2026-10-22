"""A tau2 agent whose state-changing actions are checked by Jev, TypeSafe's "System One" decision model.

The LLM runs the conversation as usual. When it proposes a write (`escalate_to_human`, `issue_refund`, `open_dispute`,
`freeze_card`), Jev answers one typed question: does the bank's policy allow this action now? If Jev says no with
enough confidence, the action is not executed: the LLM sees a "blocked by policy check" tool result and tries again
(at most MAX_BLOCKS times per turn, then the action goes through). Every Jev decision is logged to SWAPBENCH_JEV_LOG.

Registered as tau2 agent `jev_gate` by `swapbench.fintech.run` when SWAPBENCH_JEV=1. Key: JEV_API_KEY (or
TYPESAFE_API_KEY). Env: SWAPBENCH_JEV_MODEL (default jev-latest), SWAPBENCH_JEV_MIN_CONF (default 0.7).
"""
import json
import os
import time
import urllib.error
import urllib.request

from tau2.agent.llm_agent import LLMAgent
from tau2.data_model.message import AssistantMessage, ToolMessage
from tau2.utils.llm_utils import generate

URL = "https://api.typesafe.ai/v1/systemone"
MODEL = os.environ.get("SWAPBENCH_JEV_MODEL", "jev-latest")
MIN_CONF = float(os.environ.get("SWAPBENCH_JEV_MIN_CONF", "0.7"))
# Per-action thresholds, from scoring Jev on recorded decisions (scripts/jev_calibrate.py, Oct 15): at 0.5 Jev blocked
# 60% of wrong handoffs and 6% of right ones; for the other actions 0.7 keeps wrong blocks of right actions at 0-7%.
THRESHOLD = {"escalate_to_human": float(os.environ.get("SWAPBENCH_JEV_MIN_CONF_ESCALATE", "0.5"))}
MAX_BLOCKS = 2
LOG = os.environ.get("SWAPBENCH_JEV_LOG")

# One question per write tool, written from the bank's policy (swapbench/fintech/policy.md) and its clarifications
# (policy_addendum.md: never offer a transfer; an ineligible request gets an explanation, not a handoff). Today is 2026-10-01.
RULES = {
    "escalate_to_human": (
        "The support agent wants to hand this conversation to a human specialist. Does the bank's policy allow it now?",
        {"allowed": "One of these holds: identity verification has failed twice in this conversation (reason "
                    "identity_verification_failed); a duplicate charge is over $500 (refund_over_limit); the customer "
                    "asked for a human, a manager or a specialist on their own, before the agent mentioned or offered a "
                    "transfer (customer_request); or the customer asked for a service the bank's support does not "
                    "offer at all, such as a credit limit change, a loan or a new account (out_of_scope). The reason "
                    "given matches the situation.",
         "not_allowed": "None of those holds. In particular: the agent itself offered, suggested or mentioned a transfer "
                        "and the customer agreed; or the request is a fee refund, duplicate charge, dispute or card "
                        "freeze that is simply not eligible, which the agent should explain instead of handing off; or "
                        "the customer only asked a question the agent can answer."}),
    "issue_refund": (
        "The support agent wants to issue this refund. Does the bank's policy allow exactly this refund now?",
        {"allowed": "The customer's identity was verified and they said yes to this exact refund. It is either a fee "
                    "refund (fee_refund) for an overdraft, late_payment or foreign_transaction fee (never an ATM fee), "
                    "for the fee amount capped at $40.00, with no fee_refund transaction on any of the customer's "
                    "accounts in the 365 days before 2026-10-01 and no other fee refund in this conversation; or a "
                    "duplicate charge refund (duplicate_charge) for the later of two posted purchases on the same "
                    "account with the same merchant and amount within 2 days of each other, for its full amount, "
                    "at most $500.00.",
         "not_allowed": "Any of those conditions fails: wrong transaction, wrong amount, ineligible fee, a fee refund "
                        "already in the last 365 days, not a real duplicate, over $500, not verified, or not confirmed."}),
    "open_dispute": (
        "The support agent wants to open this dispute. Does the bank's policy allow exactly this dispute now?",
        {"allowed": "The customer is verified and said yes. The transaction is a posted purchase (not pending) dated on "
                    "or after 2026-08-02, not already disputed, and the reason matches what the customer said "
                    "(item_not_received, incorrect_amount or unauthorized). For unauthorized charges the card used was "
                    "frozen first with reason suspected_fraud.",
         "not_allowed": "Any of those conditions fails."}),
    "freeze_card": (
        "The support agent wants to freeze this card. Does the bank's policy allow exactly this freeze now?",
        {"allowed": "The customer is verified, asked for the freeze or reported an unauthorized charge on this card, "
                    "and said yes. The reason is lost_or_stolen for a lost or stolen card, suspected_fraud before an "
                    "unauthorized-charge dispute, and customer_request otherwise. It is the card the customer means.",
         "not_allowed": "Any of those conditions fails, or it is the wrong card."}),
}


def _key():
    return os.environ.get("JEV_API_KEY") or os.environ.get("TYPESAFE_API_KEY")


def _render(messages, proposed, max_chars=12000):
    lines = []
    for m in messages:
        role = getattr(m, "role", "")
        if role == "user":
            lines.append(f"Customer: {m.content}")
        elif role == "assistant":
            if m.content:
                lines.append(f"Agent: {m.content}")
            for t in m.tool_calls or []:
                lines.append(f"Agent calls {t.name}({json.dumps(t.arguments)})")
        elif role == "tool":
            lines.append(f"Tool result: {str(m.content)[:1500]}")
    text = "\n".join(lines)[-max_chars:]
    return f"{text}\n\nPROPOSED ACTION: {proposed.name}({json.dumps(proposed.arguments)})"


def ask_jev(state_text, tool_name, retries=3):
    q, criteria = RULES[tool_name]
    body = json.dumps({"model": MODEL, "state": state_text,
                       "questions": {"policy": {"type": "choice", "instructions": q, "criteria": criteria}}}).encode()
    req = urllib.request.Request(URL, data=body, headers={"Authorization": f"Bearer {_key()}",
                                                          "Content-Type": "application/json",
                                                          "User-Agent": "swapbench/0.1"})
    for attempt in range(retries):
        try:
            t0 = time.time()
            r = json.load(urllib.request.urlopen(req, timeout=60))
            a = r["answers"]["policy"]
            return dict(choice=a["choice"], confidence=a.get("confidence"), model=r.get("model"),
                        usage=r.get("usage"), latency_s=round(time.time() - t0, 3))
        except (urllib.error.URLError, TimeoutError, KeyError) as e:
            if attempt == retries - 1:
                return dict(choice="error", error=str(e)[:200])
            time.sleep(2 ** attempt)


class JevGateAgent(LLMAgent):
    def _generate_next_message(self, message, state):
        msg = super()._generate_next_message(message, state)
        for _ in range(MAX_BLOCKS):
            writes = [t for t in (msg.tool_calls or []) if t.name in RULES]
            if not writes:
                return msg
            t = writes[0]
            d = ask_jev(_render(state.messages, t), t.name)
            blocked = d.get("choice") == "not_allowed" and (d.get("confidence") or 0) >= THRESHOLD.get(t.name, MIN_CONF)
            if LOG:
                with open(LOG, "a") as f:
                    f.write(json.dumps(dict(tool=t.name, arguments=t.arguments, blocked=blocked, **d)) + "\n")
            if not blocked:
                return msg
            # Not executed: show the model its own attempt and the refusal, then let it try again.
            state.messages.append(msg)
            state.messages.extend(ToolMessage(id=c.id, role="tool", requestor="assistant", error=True,
                                              content=("Blocked by the automated policy check: the bank's policy does "
                                                       f"not allow {c.name} with these arguments now. Re-read the "
                                                       "policy, then explain to the customer or take a different step.")
                                              if c is t else "Not executed.")
                                  for c in msg.tool_calls)
            msg = generate(model=self.llm, tools=self.tools, messages=state.system_messages + state.messages,
                           call_name="agent_response", **self.llm_args)
        return msg


def create_jev_gate_agent(tools, domain_policy, **kwargs):
    return JevGateAgent(tools=tools, domain_policy=domain_policy, llm=kwargs.get("llm"), llm_args=kwargs.get("llm_args"))


def register():
    from tau2.registry import registry
    registry.register_agent_factory(create_jev_gate_agent, "jev_gate")
