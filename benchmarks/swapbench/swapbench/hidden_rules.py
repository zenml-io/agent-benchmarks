"""Hidden business rules for the bank: rules the bank "really" follows that are NOT in the agent's written policy.

Used by the expert-deciders benchmark (experiments/expert_deciders.md). Only the grader and the simulated experts see
these rules; the agents and the deciders under test never do. Each rule changes what the correct action is, so the
hidden-rule gold (`adjust_task`) stays satisfiable, and each is checkable from the conversation, the proposed action
and the bank's starting data (`violations`).

Decision points: escalate_to_human (handoff), issue_refund (refund), freeze_card (card action).
"""
import copy
import json
import re

CREDIT_LIMIT = re.compile(r"credit[ -]?(card )?limit", re.I)

RULES = {
    "H1": ("handoff", "Credit limit increase requests are never handed to a human: tell the customer to request the "
                      "increase in the mobile app. Do not escalate them as out of scope."),
    "H2": ("handoff", "When identity verification fails twice, do not hand off to a human: tell the customer to visit a "
                      "branch with photo ID, and take no other action."),
    "R1": ("refund", "Duplicate-charge refunds over $300.00 are not issued by the agent: hand them to a human with "
                     "reason refund_over_limit instead (the written $500 limit is out of date)."),
    "R2": ("refund", "Fee refunds only for fees dated in the last 30 days (on or after 2026-09-01); older fees are not "
                     "refunded, even if otherwise eligible. Explain this to the customer."),
    "C1": ("card", "For an unauthorized charge under $150.00, do not freeze the card: open the dispute only. Freeze for "
                   "suspected fraud only when the unauthorized charge is $150.00 or more."),
}
POINT = {"escalate_to_human": "handoff", "issue_refund": "refund", "freeze_card": "card"}


def _norm(messages):
    out = []
    for m in messages:
        role = m["role"] if isinstance(m, dict) else m.role
        content = (m.get("content") if isinstance(m, dict) else getattr(m, "content", "")) or ""
        tcs = (m.get("tool_calls") if isinstance(m, dict) else getattr(m, "tool_calls", None)) or []
        tcs = [t if isinstance(t, dict) else {"name": t.name, "arguments": t.arguments} for t in tcs]
        out.append((role, str(content), tcs))
    return out


def _amount(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return 0.0


def violations(messages, name, args, db):
    """Hidden-rule ids violated by proposing `name(args)` after `messages`, given the starting bank `db` (dict)."""
    point = POINT.get(name)
    if not point:
        return []
    msgs = _norm(messages)
    said = " ".join(c for r, c, _ in msgs if r == "user")
    v = []
    if point == "handoff":
        reason = args.get("reason")
        if reason == "out_of_scope" and CREDIT_LIMIT.search(said):
            v.append("H1")
        if reason == "identity_verification_failed":
            v.append("H2")
    elif point == "refund":
        txn = db["transactions"].get(str(args.get("transaction_id")))
        if args.get("reason") == "duplicate_charge" and _amount(args.get("amount")) > 300:
            v.append("R1")
        if args.get("reason") == "fee_refund" and txn and txn["date"] < "2026-09-01":
            v.append("R2")
    elif point == "card":
        if args.get("reason") == "suspected_fraud":
            card = str(args.get("card_id"))
            # the unauthorized charge the customer is reporting: the latest undisputed purchase on this card that the
            # customer mentions by amount, else the largest purchase on the card in the last 60 days
            txns = [t for t in db["transactions"].values() if t.get("card_id") == card and t["kind"] == "purchase"]
            named = [t for t in txns if f"{t['amount']:.2f}" in said]
            target = max(named or txns, key=lambda t: t["amount"]) if (named or txns) else None
            if target is not None and target["amount"] < 150:
                v.append("C1")
    return v


def adjust_task(task, db):
    """Gold actions under the hidden rules (a deep copy of the tau2 task)."""
    t = copy.deepcopy(task)
    crit = t.get("evaluation_criteria") or {}
    reason_for_call = json.dumps(t.get("user_scenario", {}))
    acts, out = crit.get("actions") or [], []
    unauth = {a["arguments"].get("transaction_id") for a in acts
              if a["name"] == "open_dispute" and a["arguments"].get("reason") == "unauthorized"}
    for a in acts:
        n, g = a["name"], a["arguments"]
        if n == "escalate_to_human" and g.get("reason") == "out_of_scope" and CREDIT_LIMIT.search(reason_for_call):
            continue                                                            # H1
        if n == "escalate_to_human" and g.get("reason") == "identity_verification_failed":
            continue                                                            # H2
        if n == "issue_refund" and g.get("reason") == "duplicate_charge" and _amount(g.get("amount")) > 300:
            b = copy.deepcopy(a)                                                # R1
            b["name"], b["arguments"] = "escalate_to_human", {"reason": "refund_over_limit",
                                                              "summary": "duplicate charge refund over $300"}
            out.append(b)
            continue
        if n == "issue_refund" and g.get("reason") == "fee_refund":
            txn = db["transactions"].get(g.get("transaction_id"))
            if txn and txn["date"] < "2026-09-01":
                continue                                                        # R2
        if n == "freeze_card" and g.get("reason") == "suspected_fraud":
            small = [x for x in unauth if x in db["transactions"] and db["transactions"][x]["card_id"] == g.get("card_id")
                     and db["transactions"][x]["amount"] < 150]
            if small:
                continue                                                        # C1
        out.append(a)
    crit["actions"] = out
    t["evaluation_criteria"] = crit
    return t


def rules_text(point=None):
    return "\n".join(f"- {t}" for rid, (p, t) in RULES.items() if point in (None, p))
