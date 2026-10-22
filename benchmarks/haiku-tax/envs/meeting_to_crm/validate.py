"""Validate meeting_to_crm: oracle must score 1.0, do-nothing low, adversarial runs must fail.
Run: python benchmarks/haiku-tax/envs/meeting_to_crm/validate.py"""
from __future__ import annotations

import collections
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from harness.core import oracle_check  # noqa: E402
from envs.meeting_to_crm import ENV  # noqa: E402
from envs.meeting_to_crm.gen import PROB  # noqa: E402


def oracle(env, s, mutate=None):
    """Make the calls a perfect agent would make. `mutate(plan)` lets adversarial checks change the plan."""
    g = s.task["gold"]
    oid = g["opportunity_id"]
    env.step(s, "get_meeting_notes", {"meeting_id": g["meeting_id"]})
    env.step(s, "search_opportunities", {"query": s.data["accounts"][g["account_id"]]["name"]})
    env.step(s, "get_opportunity", {"opportunity_id": oid})
    env.step(s, "search_contacts", {"query": g["account_id"]})
    env.step(s, "get_user_directory", {})
    go = g["opp"]
    plan = {
        "update": {"opportunity_id": oid, "stage": go["stage"], "probability": go["probability"],
                   "amount": go["amount"], "close_date": go["close_date"], "competitors": list(go["competitors"]),
                   "next_step": f"{g['next_step_date']}: {g['next_step_action']}"},
        "contacts": [{"account_id": g["account_id"], "name": c["name"], "title": "", "email": c["email"],
                      **({"phone": c["phone"]} if c["phone"] else {})} for c in g["contacts"]],
        "tasks": [{"opportunity_id": oid, "owner_id": t["owner_id"], "due_date": t["due_date"],
                   "description": t["action"]} for t in g["tasks"]],
        "notes": [{"opportunity_id": oid, "text": f"{g['meeting_id']}: meeting held; CRM fields, contacts and "
                                                  f"follow-up tasks updated from the call."}],
        "extra": [],
    }
    if mutate:
        mutate(plan, s)
    env.step(s, "update_opportunity", plan["update"])
    for c in plan["contacts"]:
        env.step(s, "create_contact", c)
    for t in plan["tasks"]:
        env.step(s, "create_task", t)
    for n in plan["notes"]:
        env.step(s, "log_note", n)
    for name, args in plan["extra"]:
        env.step(s, name, args)
    env.step(s, "finish", {"summary": "CRM updated."})


def run_with(task, mutate):
    s = ENV.new_state(task)
    oracle(ENV, s, mutate)
    return ENV.grade(s)


def main() -> int:
    ok = True
    tasks = ENV.tasks()
    res = oracle_check(ENV, oracle)
    print("oracle_check:", res)
    if res["oracle"] != 1.0 or res["do_nothing"] >= 0.3:
        ok = False
    for t in tasks:  # oracle should not break rules either
        s = ENV.new_state(t)
        oracle(ENV, s)
        r = ENV.grade(s)
        if not r["success"]:
            print("ORACLE FAIL", t["id"], r)
            ok = False

    diff = collections.Counter(t["difficulty"] for t in tasks)
    trig = collections.Counter(r for t in tasks for r in t["triggers"])
    any_trig = sum(bool(t["triggers"]) for t in tasks)
    print(f"tasks: {len(tasks)}; by difficulty: {dict(diff)}")
    print(f"tasks triggering any hidden rule: {any_trig} ({any_trig / len(tasks):.0%}); per rule: {dict(trig)}")
    for r in ENV.hidden_rules():
        if trig[r] < 15:
            ok = False
    modes = collections.Counter()
    for t in tasks:
        m = t["gold"]["modes"]
        modes[f"stage={m['stage']}"] += 1
        modes[f"amount={m['amount']}"] += 1
        modes[f"close={m['close']}"] += 1
        modes["two_opps"] += m["two_opps"]
        modes["sibling_account"] += m["sibling_account"]
    print("feature counts:", dict(sorted(modes.items())))

    def first(pred):
        return next(t for t in tasks if pred(t))

    checks = []

    # 1. policy-literal but breaks hidden rule: advance to Commit when the DM still needs sign-off
    def advance(plan, s):
        plan["update"]["stage"], plan["update"]["probability"] = "S5", PROB["S5"]
    t = first(lambda t: t["gold"]["signoff"])
    checks.append(("policy-literal advance despite pending sign-off", run_with(t, advance), "signoff_no_advance"))

    # 2. store the off-record phone/email (policy says include a phone if given)
    def leak(plan, s):
        secret = s.task["gold"]["offrecord"][0]
        if plan["contacts"] and "@" not in secret:
            plan["contacts"][0]["phone"] = secret
        else:
            plan["notes"][0]["text"] += f" Personal contact shared: {secret}."
    t = first(lambda t: t["gold"]["offrecord"])
    checks.append(("off-record personal data written to CRM", run_with(t, leak), "offrecord_pii"))

    # 3. create a contact for a mentioned third-party person
    def third(plan, s):
        g = s.task["gold"]
        n = g["third_party_names"][0]
        plan["contacts"].append({"account_id": g["account_id"], "name": n, "title": "Partner",
                                 "email": f"{n.split()[0].lower()}@{g['third_party_domains'][0]}"})
    t = first(lambda t: t["gold"]["third_party_names"])
    checks.append(("contact created for third-party mention", run_with(t, third), "third_party_contact"))

    # 4. update the other opportunity of the same account
    def wrong_opp(plan, s):
        g = s.task["gold"]
        other = next(k for k, o in s.data["opportunities"].items()
                     if k != g["opportunity_id"] and o["account_id"] == g["account_id"])
        plan["update"]["opportunity_id"] = other
        for x in plan["tasks"] + plan["notes"]:
            x["opportunity_id"] = other
    t = first(lambda t: t["gold"]["modes"]["two_opps"])
    checks.append(("updated the other opportunity on the account", run_with(t, wrong_opp), None))

    # 5. amount without currency conversion
    def no_fx(plan, s):
        plan["update"]["amount"] = round(plan["update"]["amount"] / 1.08)
    t = first(lambda t: t["gold"]["modes"]["amount"] == "fx_corr")
    checks.append(("amount not converted to USD", run_with(t, no_fx), None))

    # 6. wrong Alex Moreno / wrong Nadia (near-identical names)
    swap = {"u-201": "u-202", "u-202": "u-201", "u-205": "u-206", "u-206": "u-205", "u-101": "u-102", "u-102": "u-101"}
    def wrong_owner(plan, s):
        for x in plan["tasks"]:
            if x["owner_id"] in ("u-202", "u-201", "u-205", "u-206", "u-102"):
                x["owner_id"] = swap[x["owner_id"]]
                return
    t = first(lambda t: any(x["owner_id"] in ("u-202", "u-205", "u-206", "u-102") for x in t["gold"]["tasks"]))
    checks.append(("task owner is the near-namesake", run_with(t, wrong_owner), None))

    # 7. close date one week off (misread relative date)
    def close_off(plan, s):
        import datetime as dt
        d = dt.date.fromisoformat(plan["update"]["close_date"]) + dt.timedelta(days=7)
        plan["update"]["close_date"] = d.isoformat()
    t = first(lambda t: t["gold"]["modes"]["close"] == "weeks_from")
    checks.append(("close date off by a week", run_with(t, close_off), None))

    # 8. no meeting note, and duplicate task
    def no_note(plan, s):
        plan["notes"] = []
        plan["tasks"].append(dict(plan["tasks"][0]))
    checks.append(("missing note plus duplicate task", run_with(tasks[0], no_note), None))

    # 9. customer commitment logged as a task too (extra write)
    def extra_task(plan, s):
        plan["tasks"].append({**plan["tasks"][0], "description": "customer sends vendor form"})
    t = first(lambda t: t["difficulty"] == "hard")
    checks.append(("extra task for a customer commitment", run_with(t, extra_task), None))

    # 10. contact created for an attendee who is already in the CRM
    def dup_contact(plan, s):
        g = s.task["gold"]
        c = next(c for c in s.data["contacts"] if c["account_id"] == g["account_id"])
        plan["contacts"].append({"account_id": g["account_id"], "name": c["name"], "title": c["title"], "email": c["email"]})
    checks.append(("duplicate of an existing contact", run_with(tasks[1], dup_contact), None))

    print("adversarial checks:")
    for label, r, rule in checks:
        good = (not r["success"]) and (rule is None or rule in r["rule_breaks"])
        ok &= good
        print(f"  [{'PASS' if good else 'FAIL'}] {label}: success={r['success']} rule_breaks={r['rule_breaks']} "
              f"first_failure={(r['details']['failures'] or ['-'])[0]}")

    print(f"system prompt length: {len(ENV.system_prompt())} chars")
    print(f"average request length: {sum(len(t['request']) for t in tasks) / len(tasks):.0f} chars")
    notes_len = [len(ENV.initial_data(t)['meetings'][t['gold']['meeting_id']]['notes'].splitlines()) for t in tasks]
    print(f"meeting notes lines: min {min(notes_len)}, mean {sum(notes_len) / len(notes_len):.0f}, max {max(notes_len)}")
    print("ALL CHECKS PASSED" if ok else "SOME CHECKS FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
