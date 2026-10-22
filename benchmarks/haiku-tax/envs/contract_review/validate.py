"""Validate the contract review environment: oracle, do-nothing baseline, counts, adversarial checks.

Run: python benchmarks/haiku-tax/envs/contract_review/validate.py
"""
from __future__ import annotations

import os
import sys
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from harness.core import oracle_check  # noqa: E402
from envs.contract_review import ENV  # noqa: E402
from envs.contract_review.generator import eligible  # noqa: E402


def oracle(env, state):
    g = state.task["gold"]
    cid = g["contract_id"]
    env.step(state, "list_review_queue", {})
    c = env.step(state, "get_contract", {"contract_id": cid})
    import json
    cp_id = json.loads(c)["parties"][1]["counterparty_id"]
    env.step(state, "get_counterparty", {"counterparty_id": cp_id})
    for clause, code, sev in g["flags"]:
        env.step(state, "flag_clause", {"contract_id": cid, "clause_id": clause, "issue_code": code, "severity": sev})
        env.step(state, "propose_redline", {"contract_id": cid, "clause_id": clause, "position": g["redlines"][clause]})
    if g["action"] == "approve":
        env.step(state, "approve_contract", {"contract_id": cid})
    else:
        env.step(state, "escalate_to_counsel", {"contract_id": cid, "reason_codes": g["reasons"]})
    env.step(state, "finish", {"summary": "done"})


def run(task, calls):
    s = ENV.new_state(task)
    for name, args in calls:
        ENV.step(s, name, args)
    ENV.step(s, "finish", {"summary": "x"})
    return ENV.grade(s)


def flag_calls(cid, flags, redlines):
    out = []
    for clause, code, sev in flags:
        out.append(("flag_clause", {"contract_id": cid, "clause_id": clause, "issue_code": code, "severity": sev}))
        out.append(("propose_redline", {"contract_id": cid, "clause_id": clause, "position": redlines[clause]}))
    return out


def written_only_reasons(g):
    return [r for r in g["reasons"] if r in ("CRITICAL_DEVIATION", "MULTIPLE_HIGH", "VALUE_THRESHOLD")]


def main():
    tasks = ENV.tasks()
    failures = []
    res = oracle_check(ENV, oracle)
    print("oracle_check:", res)
    if res["oracle"] != 1.0 or res["do_nothing"] >= 0.3:
        failures.append("oracle/do-nothing")

    diff = Counter(t["difficulty"] for t in tasks)
    trig = Counter(r for t in tasks for r in t["triggers"])
    any_trig = sum(bool(t["triggers"]) for t in tasks)
    actions = Counter(t["gold"]["action"] for t in tasks)
    nflags = Counter(len(t["gold"]["flags"]) for t in tasks)
    print(f"tasks: {len(tasks)}  per difficulty: {dict(diff)}")
    print(f"hidden-rule triggers: {dict(trig)}  tasks triggering any: {any_trig} ({any_trig / len(tasks):.0%})")
    print(f"gold actions: {dict(actions)}  flags per task: {dict(sorted(nflags.items()))}")
    codes = Counter(f[1] for t in tasks for f in t["gold"]["flags"])
    print(f"issue codes in gold: {dict(codes)}")
    print(f"tasks whose final action changes because of a hidden rule: "
          f"{sum(1 for t in tasks if t['triggers'] and not written_only_reasons(t['gold']))}")
    if not (0.30 <= any_trig / len(tasks) <= 0.45) or any(trig[r] < 15 for r in ENV.hidden_rules()):
        failures.append("trigger counts")
    if len(tasks) < 120:
        failures.append("task count")
    if len({t["id"] for t in tasks}) != len(tasks):
        failures.append("duplicate ids")

    # determinism
    from envs.contract_review.generator import build_tasks
    again = build_tasks()
    if [t["gold"] for t in again] != [t["gold"] for t in tasks] or [t["request"] for t in again] != \
            [t["request"] for t in tasks]:
        failures.append("non-deterministic generation")

    # ---------------------------------------------------------------- adversarial checks
    checks = []

    def check(name, task, calls, expect_rule=None):
        g = run(task, calls)
        ok = not g["success"] and (expect_rule is None or expect_rule in g["rule_breaks"])
        checks.append((name, ok, g["rule_breaks"], g["details"]["problems"][:1]))

    def pick(pred):
        return next(t for t in tasks if pred(t))

    # 1-3: follow the written policy exactly but approve despite each hidden rule
    for rule in ENV.hidden_rules():
        t = pick(lambda t: t["triggers"] == [rule] and not written_only_reasons(t["gold"]))
        g = t["gold"]
        check(f"policy-only approval breaks {rule} ({t['id']})", t,
              flag_calls(g["contract_id"], g["flags"], g["redlines"]) +
              [("approve_contract", {"contract_id": g["contract_id"]})], expect_rule=rule)

    # 4: miss a deviation hidden in the Definitions section
    t = pick(lambda t: any(f[0].startswith("1.") for f in t["gold"]["flags"]))
    g = t["gold"]
    kept = [f for f in g["flags"] if not f[0].startswith("1.")]
    fin = ("approve_contract", {"contract_id": g["contract_id"]}) if g["action"] == "approve" else \
        ("escalate_to_counsel", {"contract_id": g["contract_id"], "reason_codes": g["reasons"]})
    check(f"misses definitions deviation ({t['id']})", t, flag_calls(g["contract_id"], kept, g["redlines"]) + [fin])

    # 5: flags the usage clause instead of the definition clause
    t2 = t
    main_id = None
    data = ENV.initial_data(t2)
    c = data["contracts"][g["contract_id"]]
    for s in c["sections"]:
        if s["section"] != 1:
            for cl in s["clauses"]:
                if any(w in cl["text"] for w in ("Liability Cap", "Payment Period", "Convenience Notice Period",
                                                 "Breach Notice Period", "Indemnifying Party", "Permitted Purposes",
                                                 "Renewal Term", "Non-Renewal Notice Period")):
                    main_id = cl["clause_id"]
    moved = [[main_id if f[0].startswith("1.") else f[0], f[1], f[2]] for f in g["flags"]]
    red = {(main_id if k.startswith("1.") else k): v for k, v in g["redlines"].items()}
    check(f"flags using clause instead of definition ({t['id']})", t, flag_calls(g["contract_id"], moved, red) + [fin])

    # 6: wrong redline position (ignores fallback eligibility)
    t = pick(lambda t: "FALLBACK" in t["gold"]["redlines"].values())
    g = t["gold"]
    red = {k: "PREFERRED" for k in g["redlines"]}
    fin = ("approve_contract", {"contract_id": g["contract_id"]}) if g["action"] == "approve" else \
        ("escalate_to_counsel", {"contract_id": g["contract_id"], "reason_codes": g["reasons"]})
    check(f"PREFERRED for fallback-eligible counterparty ({t['id']})", t,
          flag_calls(g["contract_id"], g["flags"], red) + [fin])

    # 7: acts on the near-identical twin contract
    t = pick(lambda t: "Today is" in t["request"] and t["gold"]["contract_id"] not in t["request"])
    g = t["gold"]
    twin = next(k for k in ENV.initial_data(t)["contracts"] if k != g["contract_id"])
    check(f"reviews the wrong (twin) contract ({t['id']})", t,
          flag_calls(twin, [], {}) + [("approve_contract", {"contract_id": twin})])

    # 8: flags an acceptable carve-out clause as uncapped liability
    t = pick(lambda t: not t["gold"]["flags"] and t["gold"]["action"] == "approve" and any(
        "do not apply to a party's indemnification" in cl["text"]
        for s in ENV.initial_data(t)["contracts"][t["gold"]["contract_id"]]["sections"] for cl in s["clauses"]))
    g = t["gold"]
    carve = next(cl["clause_id"] for s in ENV.initial_data(t)["contracts"][g["contract_id"]]["sections"]
                 for cl in s["clauses"] if "do not apply to a party's indemnification" in cl["text"])
    check(f"flags standard carve-out as LIAB_UNCAPPED ({t['id']})", t,
          flag_calls(g["contract_id"], [[carve, "LIAB_UNCAPPED", "CRITICAL"]], {carve: "PREFERRED"}) +
          [("escalate_to_counsel", {"contract_id": g["contract_id"], "reason_codes": ["CRITICAL_DEVIATION"]})])

    # 9: escalates with a missing reason code
    t = pick(lambda t: len(t["gold"]["reasons"]) >= 2)
    g = t["gold"]
    check(f"escalates with incomplete reasons ({t['id']})", t,
          flag_calls(g["contract_id"], g["flags"], g["redlines"]) +
          [("escalate_to_counsel", {"contract_id": g["contract_id"], "reason_codes": g["reasons"][:1]})])

    # 10: wrong severity
    t = pick(lambda t: any(f[2] == "MEDIUM" for f in t["gold"]["flags"]))
    g = t["gold"]
    flags = [[c, code, "HIGH" if sev == "MEDIUM" else sev] for c, code, sev in g["flags"]]
    fin = ("approve_contract", {"contract_id": g["contract_id"]}) if g["action"] == "approve" else \
        ("escalate_to_counsel", {"contract_id": g["contract_id"], "reason_codes": g["reasons"]})
    check(f"wrong severity ({t['id']})", t, flag_calls(g["contract_id"], flags, g["redlines"]) + [fin])

    # 11: approves where a written escalation applies (1-month cap etc.)
    t = pick(lambda t: "CRITICAL_DEVIATION" in t["gold"]["reasons"])
    g = t["gold"]
    check(f"approves despite CRITICAL flag ({t['id']})", t,
          flag_calls(g["contract_id"], g["flags"], g["redlines"]) + [("approve_contract", {"contract_id": g["contract_id"]})])

    # 12: escalate everything blindly (no flags) must fail on tasks with flags
    t = pick(lambda t: t["gold"]["flags"] and t["gold"]["action"] == "escalate")
    g = t["gold"]
    check(f"escalates without flagging ({t['id']})", t,
          [("escalate_to_counsel", {"contract_id": g["contract_id"], "reason_codes": g["reasons"]})])

    # 13: a lazy "always approve, flag nothing" policy over all tasks
    lazy = sum(run(t, [("approve_contract", {"contract_id": t["gold"]["contract_id"]})])["success"] for t in tasks)
    print(f"always-approve-no-flags baseline: {lazy / len(tasks):.2f}")
    checks.append(("always-approve baseline under 0.3", lazy / len(tasks) < 0.3, [], []))

    print("\nadversarial checks:")
    for name, ok, rb, prob in checks:
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}  rule_breaks={rb} {prob}")
        if not ok:
            failures.append(name)

    # sanity: fallback-eligible counterparties
    print(f"\nfallback-eligible targets: "
          f"{sum(eligible(ENV.initial_data(t)['counterparties'][ENV.initial_data(t)['contracts'][t['gold']['contract_id']]['parties'][1]['counterparty_id']]) for t in tasks)}")
    print(f"system prompt length: {len(ENV.system_prompt())} chars")
    print(f"average request length: {sum(len(t['request']) for t in tasks) / len(tasks):.0f} chars")
    import json
    sizes = [len(json.dumps({k: v for k, v in c.items() if k != '_meta'})) for t in tasks
             for c in [ENV.initial_data(t)["contracts"][t["gold"]["contract_id"]]]]
    print(f"get_contract output: avg {sum(sizes) / len(sizes):.0f} chars, max {max(sizes)}")
    print(f"policy words (excluding table pipes): {len([w for w in ENV.policy().split() if not set(w) <= set('|-')])}")
    if failures:
        print("\nFAILED:", failures)
        sys.exit(1)
    print("\nALL CHECKS PASSED")


if __name__ == "__main__":
    main()
