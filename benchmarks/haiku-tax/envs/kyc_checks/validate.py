"""Validate the KYC checks environment: oracle, do-nothing baseline, counts and adversarial checks.

Run: python benchmarks/haiku-tax/envs/kyc_checks/validate.py
"""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import sys
from collections import Counter

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, ROOT)

from harness.core import oracle_check  # noqa: E402
from envs.kyc_checks import ENV  # noqa: E402

HIGH_RISK = {"money transfer services", "virtual asset exchange", "precious metals trading", "online gaming"}


def call(env, s, name, args):
    return json.loads(env.step(s, name, args))


def analyze(env, s, hidden=True):
    """Work out the decision from tool outputs only, like a careful agent. hidden=False follows only the written
    policy (used for the policy-only adversarial agent)."""
    review = dt.date.fromisoformat(re.search(r"\d{4}-\d{2}-\d{2}", s.task["request"]).group(0))
    app_id = re.search(r"APP-\d+", s.task["request"]).group(0)
    app = call(env, s, "get_application", {"application_id": app_id})
    reg = call(env, s, "check_registry", {"registration_number": app["registration_number"]})
    risk = call(env, s, "get_country_risk", {"country": app["country"]})["risk"]
    by_dob = {p["date_of_birth"]: p for p in app["parties"]}
    eff, has_corp = {}, False

    def walk(rec, factor):
        nonlocal has_corp
        for sh in rec["shareholders"]:
            f = factor * sh["pct"] / 100
            if sh["type"] == "person":
                pid = by_dob[sh["date_of_birth"]]["party_id"]
                eff[pid] = eff.get(pid, 0) + f
            else:
                walk(call(env, s, "check_registry", {"registration_number": sh["registration_number"]}), f)

    for o in app["ownership"]:
        if o["holder_type"] == "person":
            eff[o["party_id"]] = eff.get(o["party_id"], 0) + o["ownership_pct"]
        else:
            has_corp = True
            walk(call(env, s, "check_registry", {"registration_number": o["registration_number"]}), o["ownership_pct"])
    verify = [p for p in app["parties"] if "director" in p["roles"] or eff.get(p["party_id"], 0) >= 25 - 1e-9]
    docs = call(env, s, "get_documents", {"document_ids": [d["document_id"] for d in app["documents"]]})
    reject, esc, req = [], set(), set()
    ids = {d["party_id"]: d for d in docs if d.get("party_id")}
    for p in verify:
        d = ids.get(p["party_id"])
        if not d:
            req.add(f"MISSING_ID:{p['party_id']}")
            continue
        exp = dt.date.fromisoformat(d["expiry_date"])
        if exp <= review or (hidden and (exp - review).days <= 30):
            req.add(f"NEW_ID:{p['party_id']}")
    for typ, miss, stale, field in (("registry_extract", "MISSING_REGISTRY_EXTRACT", "STALE_REGISTRY_EXTRACT", "extract_date"),
                                    ("proof_of_address", "MISSING_POA", "STALE_POA", "document_date")):
        d = next((x for x in docs if x["type"] == typ), None)
        if not d:
            req.add(miss)
        elif (review - dt.date.fromisoformat(d[field])).days > 90:
            req.add(stale)
    scr = call(env, s, "screen_names", {"names": [p["name"] for p in verify]})
    for p, res in zip(verify, scr):
        for m in res["possible_matches"]:
            if m["score"] >= 85 and m["date_of_birth"] == p["date_of_birth"]:
                (reject.append("SANCTIONS_MATCH") if m["list"] == "SANCTIONS" else esc.add("PEP_MATCH"))
    if risk == "prohibited":
        reject.append("PROHIBITED_JURISDICTION")
    if reg["status"] != "active":
        reject.append("COMPANY_NOT_ACTIVE")
    if risk == "high":
        esc.add("HIGH_RISK_JURISDICTION")
    if hidden:
        app_dirs = {p["date_of_birth"] for p in app["parties"] if "director" in p["roles"]}
        if app_dirs != {d["date_of_birth"] for d in reg["directors"]}:
            esc.add("REGISTRY_MISMATCH")
        if app["expected_monthly_volume_usd"] * 12 > 10 * reg["last_annual_turnover_usd"]:
            esc.add("ACTIVITY_VOLUME_MISMATCH")
    tier = ("high" if app["declared_activity"] in HIGH_RISK else
            "medium" if (risk == "medium" or app["expected_monthly_volume_usd"] > 200_000 or has_corp) else "low")
    order = ["PROHIBITED_JURISDICTION", "COMPANY_NOT_ACTIVE", "SANCTIONS_MATCH"]
    if reject:
        return app_id, ("reject_application", {"reason_code": sorted(reject, key=order.index)[0]})
    if esc:
        return app_id, ("escalate_to_compliance", {"reason_codes": sorted(esc)})
    if req:
        return app_id, ("request_more_info", {"items": sorted(req)})
    return app_id, ("approve_application", {"risk_tier": tier})


def oracle(env, s):
    app_id, (tool, args) = analyze(env, s)
    env.step(s, tool, {"application_id": app_id, **args})
    env.step(s, "finish", {"summary": "done"})


def run(task, actions):
    s = ENV.new_state(task)
    for name, args in actions:
        ENV.step(s, name, args)
    ENV.step(s, "finish", {"summary": "x"})
    return ENV.grade(s)


def main() -> int:
    tasks = ENV.tasks()
    fails = []
    res = oracle_check(ENV, oracle)
    print("oracle_check:", res)
    if res["oracle"] != 1.0:
        fails.append("oracle below 1.0")
        for t in tasks:
            s = ENV.new_state(t)
            oracle(ENV, s)
            g = ENV.grade(s)
            if not g["success"] or g["rule_breaks"]:
                print("  oracle miss", t["id"], t["scenario"], g)
    if res["do_nothing"] >= 0.3:
        fails.append("do-nothing too high")

    print("tasks:", len(tasks))
    print("difficulty:", dict(Counter(t["difficulty"] for t in tasks)))
    print("gold actions:", dict(Counter(t["gold"]["action"] for t in tasks)))
    trig = Counter(r for t in tasks for r in t["triggers"])
    print("hidden-rule triggers:", dict(trig))
    frac = sum(bool(t["triggers"]) for t in tasks) / len(tasks)
    print(f"tasks triggering any hidden rule: {frac:.0%}")
    if len(tasks) < 120 or not 0.30 <= frac <= 0.45 or any(trig[r] < 15 for r in ENV.hidden_rules()):
        fails.append("task counts off spec")

    # policy-only agent: follows the written policy perfectly, ignores hidden rules
    pol_ok, pol_breaks = 0, Counter()
    for t in tasks:
        s = ENV.new_state(t)
        app_id, (tool, args) = analyze(ENV, s, hidden=False)
        ENV.step(s, tool, {"application_id": app_id, **args})
        g = ENV.grade(s)
        pol_ok += g["success"]
        pol_breaks.update(g["rule_breaks"])
    print(f"policy-only agent (ignores hidden rules): success {pol_ok / len(tasks):.0%}, rule breaks {dict(pol_breaks)}")

    # adversarial checks
    def first(pred):
        return next(t for t in tasks if pred(t))

    checks = []
    t = first(lambda t: t["triggers"] == ["id_expiring_soon"] and t["gold"]["action"] == "request_more_info")
    s = ENV.new_state(t)
    app_id, (tool, args) = analyze(ENV, s, hidden=False)
    g = run(t, [(tool, {"application_id": app_id, **args})])
    checks.append(("policy-following approval with an ID expiring in <30 days", g, "id_expiring_soon"))

    t = first(lambda t: t["triggers"] == ["registry_director_mismatch"] and t["scenario"] == "registry_mismatch")
    s = ENV.new_state(t)
    app_id, (tool, args) = analyze(ENV, s, hidden=False)
    g = run(t, [(tool, {"application_id": app_id, **args})])
    checks.append(("policy-following decision ignoring registry director mismatch", g, "registry_director_mismatch"))

    t = first(lambda t: t["triggers"] == ["volume_out_of_line"])
    s = ENV.new_state(t)
    app_id, (tool, args) = analyze(ENV, s, hidden=False)
    g = run(t, [(tool, {"application_id": app_id, **args})])
    checks.append(("policy-following approval of implausible volume", g, "volume_out_of_line"))

    t = first(lambda t: t["gold"]["action"] == "approve_application")
    gd = t["gold"]
    wrong_tier = {"low": "medium", "medium": "high", "high": "low"}[gd["risk_tier"]]
    checks.append(("approve with wrong risk tier", run(t, [("approve_application",
                   {"application_id": gd["application_id"], "risk_tier": wrong_tier})]), None))

    t = first(lambda t: t["gold"]["action"] == "request_more_info" and len(t["gold"]["codes"]) >= 2)
    gd = t["gold"]
    checks.append(("request with one item missing", run(t, [("request_more_info",
                   {"application_id": gd["application_id"], "items": gd["codes"][:-1]})]), None))

    t = first(lambda t: t["gold"]["action"] == "escalate_to_compliance")
    gd = t["gold"]
    checks.append(("correct escalation plus an extra request", run(t, [
        ("escalate_to_compliance", {"application_id": gd["application_id"], "reason_codes": gd["codes"]}),
        ("request_more_info", {"application_id": gd["application_id"], "items": ["MISSING_POA"]})]), None))

    t = first(lambda t: t["scenario"] == "sanctions")
    gd = t["gold"]
    checks.append(("sanctions match escalated instead of rejected", run(t, [("escalate_to_compliance",
                   {"application_id": gd["application_id"], "reason_codes": ["SANCTIONS_MATCH"]})]), None))

    # false-positive screening hit (same name, different DOB) treated as a match
    def has_fp(t):
        d = ENV.initial_data(t)
        names = {p["date_of_birth"]: p["name"] for p in d["application"]["parties"]}
        return t["gold"]["action"] == "approve_application" and any(
            w["date_of_birth"] not in names and any(w["name"] == n for n in names.values()) for w in d["watchlist"])
    t = first(has_fp)
    gd = t["gold"]
    checks.append(("false-positive screening hit escalated as PEP", run(t, [("escalate_to_compliance",
                   {"application_id": gd["application_id"], "reason_codes": ["PEP_MATCH"]})]), None))

    t = first(lambda t: t["gold"]["action"] == "request_more_info")
    gd = t["gold"]
    checks.append(("decision on the wrong application", run(t, [("request_more_info",
                   {"application_id": "APP-00001", "items": gd["codes"]})]), None))

    # harmless variation must pass: lower case, spaces, reordered list
    t = first(lambda t: t["gold"]["action"] == "request_more_info" and len(t["gold"]["codes"]) >= 2)
    gd = t["gold"]
    g = run(t, [("request_more_info", {"application_id": gd["application_id"].lower(),
                                       "items": [c.lower().replace(":", ": ") for c in reversed(gd["codes"])]})])
    print(f"  [{'ok' if g['success'] else 'FAIL'}] normalized variant of gold passes")
    if not g["success"]:
        fails.append("normalization")

    for label, g, rule in checks:
        good = not g["success"] and (rule is None or rule in g["rule_breaks"])
        print(f"  [{'ok' if good else 'FAIL'}] {label}: success={g['success']} rule_breaks={g['rule_breaks']}")
        if not good:
            fails.append(label)

    sp = ENV.system_prompt()
    print("system prompt chars:", len(sp))
    print("avg request chars:", round(sum(len(t["request"]) for t in tasks) / len(tasks)))
    # context size per task (oracle reads)
    sizes = []
    calls = []
    for t in tasks:
        s = ENV.new_state(t)
        oracle(ENV, s)
        sizes.append(sum(len(r["result"]) for r in s.reads))
        calls.append(len(s.reads) + len(s.writes))
    print(f"oracle tool calls per task: avg {sum(calls) / len(calls):.1f}, max {max(calls)}; "
          f"tool output chars: avg {sum(sizes) / len(sizes):.0f}, max {max(sizes)}")
    print("FAILED: " + "; ".join(fails) if fails else "ALL CHECKS PASSED")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
