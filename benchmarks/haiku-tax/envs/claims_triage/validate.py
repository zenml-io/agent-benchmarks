"""Validate the claims triage environment: oracle, do-nothing baseline, counts and adversarial checks.

Run: python benchmarks/haiku-tax/envs/claims_triage/validate.py
"""
from __future__ import annotations

import copy
import json
import os
import sys
from collections import Counter

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, ROOT)

from harness.core import oracle_check  # noqa: E402

from envs.claims_triage import ENV, logic  # noqa: E402

TEXT_TO_EXCL = {v[0]: k for k, v in logic.EXCLUSIONS.items()}


def read_view(env, s, cid):
    """Everything a careful agent reads for one claim, through env.step only."""
    c = json.loads(env.step(s, "get_claim", {"claim_id": cid}))
    pid = c["policyholder_id"]
    fp = json.loads(env.step(s, "find_policies", {"policyholder_id": pid}))
    pols = {}
    for summ in fp["policies"]:
        p = json.loads(env.step(s, "get_policy", {"policy_number": summ["policy_number"]}))
        p["exclusions"] = [TEXT_TO_EXCL[t] for t in p["exclusions"]]
        pols[p["policy_number"]] = p
    hist = json.loads(env.step(s, "get_claim_history", {"policyholder_id": pid}))["prior_claims"]
    return {"claims": {cid: c}, "policies": pols, "history": {pid: hist},
            "policyholders": {pid: fp["policyholder"]}}


def make_agent(hidden=True, mutate=None):
    """An agent that reads through tools and applies logic.py; `mutate(view, decision)` lets checks inject mistakes."""
    def agent(env, s):
        for cid in s.task["gold"]["claim_ids"]:
            view = read_view(env, s, cid)
            view["roster"] = json.loads(env.step(s, "get_adjuster_roster", {}))["adjusters"]
            dec = logic.solve(view, [cid], hidden=hidden)[0]
            if mutate:
                dec = mutate(view, dec)
            if dec["action"] == "deny":
                env.step(s, "deny_claim", {"claim_id": cid, "reason_code": dec["reason_code"]})
            elif dec["action"] == "request_documents":
                env.step(s, "request_documents", {"claim_id": cid, "documents": list(reversed(dec["documents"]))})
            else:
                env.step(s, "route_claim", {"claim_id": cid.lower(), "queue": dec["queue"], "adjuster_id": dec["adjuster_id"]})
                env.step(s, "set_reserve", {"claim_id": cid, "amount": f"${dec['reserve']:,}"})
        env.step(s, "finish", {"summary": "done"})
    return agent


oracle = make_agent(hidden=True)


def run(agent, tasks):
    res = []
    for t in tasks:
        s = ENV.new_state(t)
        agent(ENV, s)
        res.append((t, ENV.grade(s)))
    return res


def main():
    failures = []
    tasks = ENV.tasks()

    # 1. oracle and do-nothing
    oc = oracle_check(ENV, oracle)
    print("oracle_check:", oc)
    if oc["oracle"] != 1.0 or oc["do_nothing"] >= 0.3:
        failures.append("oracle_check")
    for t, g in run(oracle, tasks):
        if g["rule_breaks"]:
            failures.append(f"oracle breaks rules on {t['id']}: {g['rule_breaks']}")

    # 2. counts
    print("tasks:", len(tasks))
    print("difficulty:", dict(Counter(t["difficulty"] for t in tasks)))
    trig = Counter(r for t in tasks for r in t["triggers"])
    print("hidden-rule triggers:", dict(trig))
    n_trig = sum(1 for t in tasks if t["triggers"])
    print(f"tasks triggering any hidden rule: {n_trig} ({n_trig / len(tasks):.0%})")
    print("claims per task:", dict(Counter(len(t["gold"]["claim_ids"]) for t in tasks)))
    print("gold outcomes:", dict(Counter(g["action"] + (":" + (g.get("queue") or g.get("reason_code") or ""))
                                         .rstrip(":") for t in tasks for g in t["gold"]["claims"])))
    if len(tasks) < 120 or any(trig[r] < 15 for r in ENV.hidden_rules()) or not (0.30 <= n_trig / len(tasks) <= 0.45):
        failures.append("counts")
    if len({t["id"] for t in tasks}) != len(tasks):
        failures.append("duplicate task ids")

    # 3. adversarial checks
    def check(name, agent, subset, must_report=None, all_fail=True):
        rs = run(agent, subset)
        fails = sum(1 for _, g in rs if not g["success"])
        reported = sum(1 for t, g in rs if must_report and must_report(t) <= set(g["rule_breaks"]))
        ok = (fails == len(rs)) if all_fail else fails > 0
        if must_report:
            ok = ok and reported == len(rs)
        print(f"adversarial [{name}]: {fails}/{len(rs)} fail" + (f", rule reported {reported}/{len(rs)}" if must_report else "")
              + ("" if ok else "  <-- CHECK FAILED"))
        if not ok:
            failures.append(name)

    triggered = [t for t in tasks if t["triggers"]]
    check("follows the written policy only, ignores hidden rules", make_agent(hidden=False), triggered,
          must_report=lambda t: set(t["triggers"]) & {"siu_recent_coverage", "duplicate_loss"} or {"adjuster_conflict"})
    for rule in ENV.hidden_rules():
        both_siu = {"siu_recent_coverage", "duplicate_loss"}
        sub = [t for t in tasks if rule in t["triggers"] and not (rule in both_siu and both_siu <= set(t["triggers"]))]
        check(f"follows everything except {rule}", make_agent(hidden=logic.ALL_RULES - {rule}), sub,
              must_report=lambda t, r=rule: {r})

    def off_by_one(view, dec):
        if dec["action"] == "route":
            dec["reserve"] += 1
        return dec
    routed = [t for t in tasks if any(g["action"] == "route" for g in t["gold"]["claims"])]
    check("reserve off by one dollar", make_agent(mutate=off_by_one), routed)

    def no_lae(view, dec):
        if dec["action"] == "route":
            dec["reserve"] = dec["net"]
        return dec
    check("reserve without loss adjustment expense", make_agent(mutate=no_lae), routed)

    def always_fast(view, dec):
        if dec["action"] == "route" and dec["queue"] != "fast_track":
            dec["queue"] = "fast_track"
        return dec
    non_fast = [t for t in routed if any(g.get("queue") not in (None, "fast_track") for g in t["gold"]["claims"])]
    check("fast-track everything", make_agent(mutate=always_fast), non_fast)

    def ignore_status(view, dec):
        if dec["action"] == "route":
            c = view["claims"][dec["claim_id"]]
            cands = [a for a in view["roster"] if a["team"] == logic.TEAM_FOR_QUEUE[dec["queue"]]
                     and (dec["queue"] == "siu_review" or c["line"] in a["lines"])
                     and (dec["queue"] == "fast_track" or c["region"] in a["regions"])
                     and not logic.conflict(a, view["policyholders"][c["policyholder_id"]])]
            cands.sort(key=lambda a: (a["open_claims"], a["adjuster_id"]))
            dec["adjuster_id"] = cands[0]["adjuster_id"]
        return dec
    leave = [t for t in tasks if any(a["status"] != "active" or a["open_claims"] >= a["max_open_claims"]
                                     for a in ENV.initial_data(t)["roster"])]
    check("ignores leave and capacity (some tasks)", make_agent(mutate=ignore_status), leave, all_fail=False)

    def deny_watery(view, dec):
        c = view["claims"][dec["claim_id"]]
        if any(w in c["description"].lower() for w in ("flood", "sewage", "river", "water")):
            return {**dec, "action": "deny", "reason_code": "DEN-EXCL"}
        return dec
    watery = [t for t in tasks if any(ENV.initial_data(t)["claims"][g["claim_id"]]["peril"] in ("burst_pipe", "sewer_backup", "flood")
                                      and g["action"] != "deny" for g in t["gold"]["claims"])]
    check("denies covered water claims by description", make_agent(mutate=deny_watery), watery)

    def extra_reserve(env_unused, s):
        oracle(ENV, s)
        for g in s.task["gold"]["claims"]:
            if g["action"] != "route":
                ENV.step(s, "set_reserve", {"claim_id": g["claim_id"], "amount": 1000})
    not_routed = [t for t in tasks if any(g["action"] != "route" for g in t["gold"]["claims"])]
    check("correct writes plus a reserve on a denied/pending claim", extra_reserve, not_routed)

    def docs_then_route(view, dec):
        return dec if dec["action"] != "request_documents" else {**dec, "action": "route", "queue": "standard",
                                                                    "adjuster_id": view["roster"][0]["adjuster_id"],
                                                                    "reserve": 1000}
    docs = [t for t in tasks if any(g["action"] == "request_documents" for g in t["gold"]["claims"])]
    check("routes claims with missing documents", make_agent(mutate=docs_then_route), docs)

    def reversed_order(env_unused, s):
        s.task = copy.deepcopy(s.task)
        s.task["gold"]["claim_ids"] = list(reversed(s.task["gold"]["claim_ids"]))
        oracle(ENV, s)
    two = [t for t in tasks if len(t["gold"]["claim_ids"]) == 2]
    rs = run(reversed_order, two)
    print(f"info [two-claim tasks handled in reverse order]: {sum(not g['success'] for _, g in rs)}/{len(rs)} fail")

    def unlisted(env_unused, s):
        oracle(ENV, s)
        ENV.step(s, "deny_claim", {"claim_id": "CLM-99999", "reason_code": "DEN-EXCL"})
    check("acts on an unlisted claim", unlisted, tasks[:20])

    # 4. how the written-policy-only agent and a sloppy agent score overall
    for name, ag in [("written policy only", make_agent(hidden=False)),
                     ("ignores leave and capacity", make_agent(mutate=ignore_status))]:
        rs = run(ag, tasks)
        print(f"info [{name}] success: {sum(g['success'] for _, g in rs) / len(rs):.2f}")

    # 5. prompt sizes
    print("system prompt chars:", len(ENV.system_prompt()))
    print("avg request chars:", round(sum(len(t["request"]) for t in tasks) / len(tasks), 1))
    sizes = []
    for t in tasks:
        s = ENV.new_state(t)
        oracle(ENV, s)
        sizes.append((len(s.reads) + len(s.writes), sum(len(r["result"]) for r in s.reads)))
    print("oracle tool calls per task: avg %.1f, max %d; tool output chars per task: avg %d, max %d" % (
        sum(x for x, _ in sizes) / len(sizes), max(x for x, _ in sizes),
        sum(y for _, y in sizes) / len(sizes), max(y for _, y in sizes)))

    if failures:
        print("FAILED:", failures)
        sys.exit(1)
    print("ALL CHECKS PASSED")


if __name__ == "__main__":
    main()
