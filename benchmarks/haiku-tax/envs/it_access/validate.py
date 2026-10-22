"""Validate the it_access environment: oracle, do-nothing baseline, counts and adversarial checks.

Run: python benchmarks/haiku-tax/envs/it_access/validate.py   (exits non-zero on any failed check)
"""
from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from harness.core import oracle_check  # noqa: E402
from envs.it_access import ENV  # noqa: E402
from envs.it_access import generate as G  # noqa: E402

FAILS: list[str] = []


def check(cond: bool, msg: str):
    print(("PASS " if cond else "FAIL ") + msg)
    if not cond:
        FAILS.append(msg)


def gold_calls(gold: dict, tid: str) -> list[tuple[str, dict]]:
    calls = [("grant_access", dict(g)) for g in gold["grants"]]
    calls += [("deny_request", dict(x)) for x in gold["denials"]]
    calls += [("request_approval", dict(x)) for x in gold["approval_requests"]]
    calls.append(("close_ticket", {"ticket_id": tid, "resolution_code": gold["resolution"]}))
    return calls


def tid_of(env, task) -> str:
    return env.initial_data(task)["ticket"]["ticket_id"]


def run(env, task, calls, reads=True):
    s = env.new_state(task)
    tid = s.data["ticket"]["ticket_id"]
    if reads:
        env.step(s, "get_ticket", {"ticket_id": tid})
        env.step(s, "get_approvals", {"ticket_id": tid})
        for it in task["gold"]["items"]:
            env.step(s, "get_employee", {"query": it["employee_id"]})
            env.step(s, "get_resource", {"query": it["resource_id"]})
            env.step(s, "get_current_access", {"employee_id": it["employee_id"]})
    for name, args in calls:
        env.step(s, name, args)
    env.step(s, "finish", {"summary": "done"})
    return s, env.grade(s)


def oracle(env, state):
    task = state.task
    tid = state.data["ticket"]["ticket_id"]
    env.step(state, "get_ticket", {"ticket_id": tid})
    env.step(state, "get_approvals", {"ticket_id": tid})
    for it in task["gold"]["items"]:
        env.step(state, "get_employee", {"query": it["employee_id"]})
        env.step(state, "get_resource", {"query": it["resource_id"]})
    for name, args in gold_calls(task["gold"], tid):
        env.step(state, name, args)
    env.step(state, "finish", {"summary": "handled"})


def first(pred):
    return next(t for t in ENV.tasks() if pred(t))


def main():
    tasks = ENV.tasks()
    res = oracle_check(ENV, oracle)
    print("oracle_check:", res)
    check(res["oracle"] == 1.0, "oracle scores 1.0")
    check(res["do_nothing"] < 0.3, "do-nothing agent scores under 0.3")

    print("\ntotal tasks:", len(tasks))
    print("per difficulty:", dict(Counter(t["difficulty"] for t in tasks)))
    trig = Counter(r for t in tasks for r in t["triggers"])
    print("tasks triggering each hidden rule:", dict(trig))
    share = sum(bool(t["triggers"]) for t in tasks) / len(tasks)
    print(f"share of tasks triggering any hidden rule: {share:.2f}")
    print("gold resolutions:", dict(Counter(t["gold"]["resolution"] for t in tasks)))
    check(len(tasks) >= 120, "at least 120 tasks")
    check(all(trig[r] >= 15 for r in ENV.hidden_rules()), "each hidden rule triggered by >= 15 tasks")
    check(0.30 <= share <= 0.45, "30-45% of tasks trigger a hidden rule")
    check(len({t["id"] for t in tasks}) == len(tasks), "task ids unique")

    # policy-only agent: follows the written policy exactly, ignores the hidden rules
    pol_ok, pol_missed = 0, []
    for t in tasks:
        _, g = run(ENV, t, gold_calls(t["policy_only"], tid_of(ENV, t)))
        pol_ok += g["success"]
        if t["triggers"]:
            if g["success"] or not set(t["triggers"]) <= set(g["rule_breaks"]):
                pol_missed.append(t["id"])
        elif not g["success"] or g["rule_breaks"]:
            pol_missed.append(t["id"])
    print(f"\npolicy-only agent (written policy, no hidden rules): {pol_ok / len(tasks):.2f}")
    check(not pol_missed, "policy-only agent fails exactly the hidden-rule tasks and the grader names the rule "
                          f"(mismatches: {pol_missed[:5]})")
    check(all(not ENV.grade(run(ENV, t, gold_calls(t["gold"], tid_of(ENV, t)))[0])["rule_breaks"] for t in tasks),
          "gold actions never break a hidden rule")

    print("\nadversarial checks:")
    for rule in ENV.hidden_rules():
        t = first(lambda t, r=rule: t["triggers"] == [r])
        _, g = run(ENV, t, gold_calls(t["policy_only"], tid_of(ENV, t)))
        check(not g["success"] and rule in g["rule_breaks"],
              f"{t['id']}: policy-compliant action that breaks hidden rule {rule} fails and reports it "
              f"(rule_breaks={g['rule_breaks']})")

    t = first(lambda t: t["gold"]["grants"] and not t["triggers"])
    calls = gold_calls(t["gold"], tid_of(ENV, t))
    from datetime import date, timedelta
    bad = [(n, dict(a)) for n, a in calls]
    bad[0][1]["expiry_date"] = (date.fromisoformat(bad[0][1]["expiry_date"]) + timedelta(days=1)).isoformat()
    check(not run(ENV, t, bad)[1]["success"], f"{t['id']}: expiry off by one day fails")
    check(not run(ENV, t, calls[:-1])[1]["success"], f"{t['id']}: missing close_ticket fails")
    extra = calls[:-1] + [("request_approval", {"ticket_id": tid_of(ENV, t), "approver_id": "E00001",
                                                "resource_id": t["gold"]["grants"][0]["resource_id"]})] + calls[-1:]
    check(not run(ENV, t, extra)[1]["success"], f"{t['id']}: extra approval request fails")
    two_close = calls + [("close_ticket", {"ticket_id": tid_of(ENV, t), "resolution_code": "DENIED"})]
    check(not run(ENV, t, two_close)[1]["success"], f"{t['id']}: two different close codes fail")
    named = [(n, dict(a)) for n, a in calls]
    named[0][1]["employee_id"] = ENV.initial_data(t)["employees"][named[0][1]["employee_id"]]["name"]
    check(not run(ENV, t, named)[1]["success"], f"{t['id']}: employee name instead of ID fails")
    loose = [(n, {k: (v.lower() if k != "role" else f" `{v.upper()}` ") for k, v in a.items()}) for n, a in calls]
    loose.append(calls[-1])
    _, g = run(ENV, t, loose)
    check(g["success"], f"{t['id']}: harmless variation (case, backticks, duplicate identical close) still succeeds")

    t = first(lambda t: t["scenario"] == "deprecated" and t["gold"]["grants"])
    it = t["gold"]["items"][0]
    calls = gold_calls(t["gold"], tid_of(ENV, t))
    calls[0][1]["role"] = it["named_role"]
    check(not run(ENV, t, calls)[1]["success"], f"{t['id']}: granting the deprecated role fails")

    t = first(lambda t: t["scenario"] == "prev_mgr" and t["gold"]["resolution"] == "PENDING_APPROVAL")
    _, g = run(ENV, t, gold_calls(t["policy_only"], tid_of(ENV, t)))  # sanity: same as gold
    o = G.solve_item(ENV.initial_data(t), t["gold"]["items"][0])
    tid = tid_of(ENV, t)
    exp = G.policy_expiry(ENV.initial_data(t), t["gold"]["items"][0],
                          ENV.initial_data(t)["employees"][o["employee_id"]],
                          ENV.initial_data(t)["resources"][o["resource_id"]]).isoformat()
    grant = [("grant_access", {"employee_id": o["employee_id"], "resource_id": o["resource_id"], "role": o["role"],
                               "expiry_date": exp}), ("close_ticket", {"ticket_id": tid, "resolution_code": "GRANTED"})]
    check(not run(ENV, t, grant)[1]["success"], f"{t['id']}: accepting the previous manager's approval fails")

    t = first(lambda t: t["scenario"] == "role_not_found")
    it = t["gold"]["items"][0]
    res = ENV.initial_data(t)["resources"][it["resource_id"]]
    rd = G.lowest_role(res, "read")["role"]
    calls = [("grant_access", {"employee_id": it["employee_id"], "resource_id": it["resource_id"], "role": rd,
                               "expiry_date": "2026-12-31"}),
             ("close_ticket", {"ticket_id": tid_of(ENV, t), "resolution_code": "GRANTED"})]
    check(not run(ENV, t, calls)[1]["success"], f"{t['id']}: substituting a similar role name fails")

    sp = ENV.system_prompt()
    print(f"\nsystem prompt length: {len(sp)} chars")
    print(f"average request length: {sum(len(t['request']) for t in tasks) / len(tasks):.0f} chars")
    print(f"policy words: {len(ENV.policy().split())}")
    if FAILS:
        print(f"\n{len(FAILS)} check(s) failed")
        sys.exit(1)
    print("\nall checks passed")


if __name__ == "__main__":
    main()
