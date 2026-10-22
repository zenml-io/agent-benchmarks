"""Validate the invoice extraction environment: oracle, do-nothing baseline, counts and adversarial checks.

Run: python benchmarks/haiku-tax/envs/invoice_extraction/validate.py
"""
from __future__ import annotations

import collections
import copy
import datetime as dt
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from harness.core import oracle_check  # noqa: E402
from envs.invoice_extraction import ENV  # noqa: E402
from envs.invoice_extraction import generator as G  # noqa: E402


def doc_write(g: dict, override: dict | None = None) -> tuple[str, dict]:
    """The gold write for one document."""
    d = g["document_id"]
    if g["action"] == "submit":
        args = {"document_id": d, **copy.deepcopy(g["fields"])}
        args.update(override or {})
        return "submit_invoice", args
    code = g["reason"] or "MANUAL_REVIEW"
    return f"{g['action']}_invoice", {"document_id": d, "reason_code": code, "note": "per AP-07"}


def oracle_doc(env, state, g):
    env.step(state, "get_document", {"document_id": g["document_id"]})
    vid = g["vendor_id"]
    v = state.data["vendors"].get(vid)
    if v:
        env.step(state, "search_vendors", {"query": v["tax_id"]})
        env.step(state, "get_vendor", {"vendor_id": vid})
        env.step(state, "list_invoices_for_vendor", {"vendor_id": vid})
    if g["action"] == "submit" and g["fields"]["po_number"]:
        env.step(state, "get_purchase_order", {"po_number": g["fields"]["po_number"]})
    name, args = doc_write(g)
    env.step(state, name, args)


def oracle(env, state):
    for g in state.task["gold"]["docs"].values():
        oracle_doc(env, state, g)
    env.step(state, "finish", {"summary": "processed"})


def run(task, plan) -> dict:
    """plan: list of (tool, args); returns grade."""
    s = ENV.new_state(task)
    for name, args in plan:
        ENV.step(s, name, args)
    ENV.step(s, "finish", {"summary": "done"})
    return ENV.grade(s)


def gold_plan(task, skip=None, replace=None):
    plan = []
    for d, g in task["gold"]["docs"].items():
        if d == skip:
            continue
        if replace and d in replace:
            plan += replace[d]
        else:
            plan.append(doc_write(g))
    return plan


def fake_submit(task, g):
    """A submit with plausible fields read off the truth, for a document whose gold is hold/reject."""
    return ("submit_invoice", {"document_id": g["document_id"], "vendor_id": g["vendor_id"], "invoice_number": "X1",
                               "invoice_date": "2026-03-01", "due_date": "2026-03-31", "currency": "USD",
                               "subtotal": 100, "tax": 0, "total": 100, "po_number": "",
                               "line_items": [{"description": "x", "quantity": 1, "unit_price": 100, "amount": 100}]})


def main() -> int:
    tasks = ENV.tasks()
    failures = []

    def check(name, cond, info=""):
        print(f"  [{'PASS' if cond else 'FAIL'}] {name}{(' - ' + info) if info else ''}")
        if not cond:
            failures.append(name)

    print("== oracle check")
    res = oracle_check(ENV, oracle)
    print(" ", res)
    check("oracle scores 1.0", res["oracle"] == 1.0)
    check("do-nothing scores under 0.3", res["do_nothing"] < 0.3)
    # oracle never breaks a hidden rule
    br = 0
    for t in tasks:
        s = ENV.new_state(t)
        oracle(ENV, s)
        br += bool(ENV.grade(s)["rule_breaks"])
    check("oracle breaks no hidden rule", br == 0)

    print("\n== counts")
    print(f"  total tasks: {len(tasks)}")
    print(f"  per difficulty: {dict(collections.Counter(t['difficulty'] for t in tasks))}")
    trig = collections.Counter(r for t in tasks for r in t["triggers"])
    print(f"  tasks triggering each hidden rule: {dict(trig)}")
    share = sum(1 for t in tasks if t["triggers"]) / len(tasks)
    print(f"  tasks triggering any hidden rule: {share:.0%}")
    ndocs = collections.Counter(len(t["gold"]["docs"]) for t in tasks)
    print(f"  documents per task: {dict(sorted(ndocs.items()))}")
    scen = collections.Counter(g["scenario"] for t in tasks for g in t["gold"]["docs"].values())
    print(f"  documents per scenario: {dict(scen)}")
    acts = collections.Counter(g["action"] for t in tasks for g in t["gold"]["docs"].values())
    print(f"  gold actions: {dict(acts)}")
    check("each hidden rule triggered by >= 15 tasks", all(trig[r] >= 15 for r in G.RULE_IDS))
    check("30-45% of tasks trigger a hidden rule", 0.30 <= share <= 0.45)
    # determinism
    again = G.build_tasks()
    check("tasks rebuild identically from the seed",
          [t["request"] for t in again] == [t["request"] for t in tasks]
          and [list(t["data"]["documents"].values()) for t in again]
          == [list(t["data"]["documents"].values()) for t in tasks])

    print("\n== adversarial checks (all must fail)")

    def first(pred):
        return next(t for t in tasks if pred(t))

    # 1. Follows the written policy (all checks pass) but submits a doc that breaks each hidden rule.
    for rule in G.RULE_IDS:
        t = first(lambda t: rule in t["triggers"])
        g = next(g for g in t["gold"]["docs"].values() if rule in g["hidden"])
        out = run(t, gold_plan(t, replace={g["document_id"]: [fake_submit(t, g)]}))
        check(f"policy-compliant submit breaking {rule} fails and reports it",
              not out["success"] and rule in out["rule_breaks"], f"{t['id']} rule_breaks={out['rule_breaks']}")

    # 2. Due date taken from the terms printed on the invoice instead of the vendor master.
    t = first(lambda t: any(g["action"] == "submit" and g["fields"]["due_date"] !=
                            (dt.date.fromisoformat(g["fields"]["invoice_date"]) + dt.timedelta(days=30)).isoformat()
                            for g in t["gold"]["docs"].values()))
    g = next(g for g in t["gold"]["docs"].values() if g["action"] == "submit" and g["fields"]["due_date"] !=
             (dt.date.fromisoformat(g["fields"]["invoice_date"]) + dt.timedelta(days=30)).isoformat())
    wrong_due = (dt.date.fromisoformat(g["fields"]["invoice_date"]) + dt.timedelta(days=30)).isoformat()
    out = run(t, gold_plan(t, replace={g["document_id"]: [doc_write(g, {"due_date": wrong_due})]}))
    check("default Net 30 due date instead of master terms fails", not out["success"], t["id"])

    # 3. Pre-tax figure reported as the total.
    t = first(lambda t: any(g["action"] == "submit" and g["fields"]["tax"] > 0 for g in t["gold"]["docs"].values()))
    g = next(g for g in t["gold"]["docs"].values() if g["action"] == "submit" and g["fields"]["tax"] > 0)
    out = run(t, gold_plan(t, replace={g["document_id"]: [doc_write(g, {"total": g["fields"]["subtotal"]})]}))
    check("pre-tax amount submitted as total fails", not out["success"], t["id"])

    # 4. Day-first date read month-first.
    def ambiguous(g, t):
        if g["action"] != "submit":
            return False
        v = t["data"]["vendors"][g["vendor_id"]]
        d = dt.date.fromisoformat(g["fields"]["invoice_date"])
        return v["country"] != "US" and d.day <= 12 and d.day != d.month
    t = first(lambda t: any(ambiguous(g, t) for g in t["gold"]["docs"].values()))
    g = next(g for g in t["gold"]["docs"].values() if ambiguous(g, t))
    d = dt.date.fromisoformat(g["fields"]["invoice_date"])
    swapped = dt.date(d.year, d.day, d.month).isoformat()
    out = run(t, gold_plan(t, replace={g["document_id"]: [doc_write(g, {"invoice_date": swapped})]}))
    check("day-first date parsed month-first fails", not out["success"], t["id"])

    # 5. Rejecting (instead of holding) a document that breaks a hidden rule.
    t = first(lambda t: "bank_mismatch" in t["triggers"])
    g = next(g for g in t["gold"]["docs"].values() if g["hidden"])
    out = run(t, gold_plan(t, replace={g["document_id"]: [("reject_invoice", {
        "document_id": g["document_id"], "reason_code": "UNKNOWN_VENDOR"})]}))
    check("reject instead of hold on a hidden-rule document fails", not out["success"], t["id"])

    # 6. Submitting a duplicate.
    t = first(lambda t: any(g["scenario"] == "duplicate" for g in t["gold"]["docs"].values()))
    g = next(g for g in t["gold"]["docs"].values() if g["scenario"] == "duplicate")
    out = run(t, gold_plan(t, replace={g["document_id"]: [fake_submit(t, g)]}))
    check("submitting a duplicate fails", not out["success"], t["id"])

    # 7. Acting on the document the requester said to leave alone.
    t = first(lambda t: t["gold"]["excluded"])
    plan = gold_plan(t) + [("hold_invoice", {"document_id": t["gold"]["excluded"], "reason_code": "MANUAL_REVIEW"})]
    out = run(t, plan)
    check("extra write on the excluded document fails", not out["success"], t["id"])

    # 8. Right action, wrong reason code.
    t = first(lambda t: any(g["scenario"] == "po_exceeded" for g in t["gold"]["docs"].values()))
    g = next(g for g in t["gold"]["docs"].values() if g["scenario"] == "po_exceeded")
    out = run(t, gold_plan(t, replace={g["document_id"]: [("hold_invoice", {
        "document_id": g["document_id"], "reason_code": "MANUAL_REVIEW"})]}))
    check("hold with the wrong reason code fails", not out["success"], t["id"])

    # 9. Multi-document request only partly handled.
    t = first(lambda t: len(t["gold"]["docs"]) >= 2)
    out = run(t, gold_plan(t, skip=list(t["gold"]["docs"])[-1]))
    check("partial multi-document handling fails", not out["success"], t["id"])

    # 10. Missing line item (freight line dropped).
    t = first(lambda t: any(g["action"] == "submit" and len(g["fields"]["line_items"]) >= 2
                            for g in t["gold"]["docs"].values()))
    g = next(g for g in t["gold"]["docs"].values() if g["action"] == "submit" and len(g["fields"]["line_items"]) >= 2)
    out = run(t, gold_plan(t, replace={g["document_id"]: [doc_write(g, {"line_items": g["fields"]["line_items"][:-1]})]}))
    check("dropping a line item fails", not out["success"], t["id"])

    # 11. Submitting the distractor vendor with a near-identical name.
    t = first(lambda t: t["difficulty"] != "easy" and any(g["action"] == "submit" for g in t["gold"]["docs"].values()))
    g = next(g for g in t["gold"]["docs"].values() if g["action"] == "submit")
    other = next(v for v in t["data"]["vendors"] if v != g["vendor_id"])
    out = run(t, gold_plan(t, replace={g["document_id"]: [doc_write(g, {"vendor_id": other})]}))
    check("wrong vendor_id fails", not out["success"], t["id"])

    print("\n== tolerance checks (must pass)")
    # Harmless variation: amounts as formatted strings, reordered line items, number in other case/separators.
    t = first(lambda t: any(g["action"] == "submit" and len(g["fields"]["line_items"]) >= 2
                            for g in t["gold"]["docs"].values()))
    g = next(g for g in t["gold"]["docs"].values() if g["action"] == "submit" and len(g["fields"]["line_items"]) >= 2)
    f = g["fields"]
    li = [{"description": l["description"].upper(), "quantity": str(l["quantity"]),
           "unit_price": f"{l['unit_price']:,.2f}", "amount": f"{l['amount']:,.2f}"} for l in f["line_items"]][::-1]
    over = {"subtotal": f"{f['subtotal']:,.2f}", "tax": str(f["tax"]), "total": f"{f['currency']} {f['total']:,.2f}",
            "invoice_number": " " + f["invoice_number"].lower().replace("-", " "), "line_items": li,
            "currency": f["currency"].lower(), "po_number": f["po_number"].replace("PO-", "")}
    out = run(t, gold_plan(t, replace={g["document_id"]: [doc_write(g, over)]}))
    check("formatted numbers, reordered items and number variants still pass", out["success"], t["id"])
    # A second action on an already-actioned document is refused and does not change the grade.
    t = first(lambda t: len(t["gold"]["docs"]) == 1 and next(iter(t["gold"]["docs"].values()))["action"] == "reject")
    g = next(iter(t["gold"]["docs"].values()))
    out = run(t, gold_plan(t) + [fake_submit(t, g)])
    check("a second action on the same document is refused", out["success"], t["id"])

    print("\n== prompt and request sizes")
    sp = ENV.system_prompt()
    print(f"  system prompt: {len(sp)} characters")
    print(f"  average request: {sum(len(t['request']) for t in tasks) / len(tasks):.0f} characters")
    dl = [len(d["text"]) for t in tasks for d in t["data"]["documents"].values()]
    print(f"  average document text: {sum(dl) / len(dl):.0f} characters (max {max(dl)})")

    print(f"\n{'ALL CHECKS PASSED' if not failures else 'FAILED: ' + ', '.join(failures)}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
