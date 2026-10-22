"""Validate the lead_qualification environment: oracle, do-nothing agent, counts and adversarial checks.

Run: python benchmarks/haiku-tax/envs/lead_qualification/validate.py
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]  # benchmarks/haiku-tax
sys.path.insert(0, str(ROOT))

from harness.core import oracle_check  # noqa: E402
from envs.lead_qualification import ENV  # noqa: E402
from envs.lead_qualification.env import REPS, solve  # noqa: E402

FAILS = []


def body_for(state, lid, rep):
    first = state.data["leads"][lid]["name"].split(" ")[0]
    return (f"Hi {first}, thanks for your interest in Quillfeather Flow. I'd be glad to show you how teams automate "
            f"approvals. Best, {REPS[rep]}")


def reads(env, s, lid, owner=None):
    lead = json.loads(env.step(s, "get_lead", {"lead_id": lid}))
    dom = lead["email"].split("@")[1]
    env.step(s, "get_company_profile", {"domain": dom})
    env.step(s, "get_crm_history", {"email": lead["email"]})
    if owner and owner != "none":
        env.step(s, "get_calendar_slots", {"rep_id": owner})


def write_gold(env, s, gold, skip_email=(), email_override=None, lead_override=None):
    for lid, g in gold.items():
        args = {"lead_id": lid, "status": g["status"], "score": g["score"], "owner": g["owner"],
                "reason_code": g["reason"]}
        if lead_override and lid in lead_override:
            args.update(lead_override[lid])
        env.step(s, "update_lead", args)
    for lid, g in gold.items():
        e = g["email"]
        if not e or lid in skip_email:
            continue
        args = {"to": s.data["leads"][lid]["email"], "template_id": e["template"], "rep_id": e["rep"],
                "slot": e["slot"] or "none", "body": body_for(s, lid, e["rep"])}
        if email_override and lid in email_override:
            args.update(email_override[lid](s, lid, args))
        env.step(s, "send_email", args)


def oracle(env, s):
    gold = s.task["gold"]["leads"]
    env.step(s, "get_territory_map", {})
    env.step(s, "get_email_templates", {})
    for lid, g in gold.items():
        reads(env, s, lid, g["owner"])
    write_gold(env, s, gold)
    env.step(s, "finish", {"summary": "done"})


def policy_only(env, s):
    """Follows the written policy perfectly but knows none of the hidden rules."""
    data = s.task["data"]
    g0 = solve(data, s.task["lead_ids"], hidden=False)
    for lid, g in g0.items():
        env.step(s, "update_lead", {"lead_id": lid, "status": g["status"], "score": g["score"], "owner": g["owner"],
                                    "reason_code": g["reason"]})
        if g["email"]:
            body = body_for(s, lid, g["email"]["rep"])
            env.step(s, "send_email", {"to": data["leads"][lid]["email"], "template_id": g["email"]["template"],
                                       "rep_id": g["email"]["rep"], "slot": g["email"]["slot"] or "none",
                                       "body": body})
    env.step(s, "finish", {"summary": "done"})


def check(name, cond, info=""):
    print(f"  [{'ok' if cond else 'FAIL'}] {name}{(': ' + info) if info and not cond else ''}")
    if not cond:
        FAILS.append(name)


def first(tasks, pred):
    for t in tasks:
        if pred(t):
            return t
    raise SystemExit(f"no task for check: {pred}")


def run_adv(task, **kw):
    s = ENV.new_state(task)
    write_gold(ENV, s, task["gold"]["leads"], **kw)
    ENV.step(s, "finish", {"summary": "x"})
    return ENV.grade(s)


def main():
    tasks = ENV.tasks()
    res = oracle_check(ENV, oracle)
    print("oracle_check:", res)
    check("oracle scores 1.0", res["oracle"] == 1.0)
    check("do-nothing scores under 0.3", res["do_nothing"] < 0.3)
    # oracle never breaks a hidden rule
    nb = 0
    for t in tasks:
        s = ENV.new_state(t)
        oracle(ENV, s)
        g = ENV.grade(s)
        if not g["success"]:
            print("   oracle failure", t["id"], g["details"])
        nb += bool(g["rule_breaks"])
    check("oracle breaks no hidden rule", nb == 0, str(nb))

    # policy-only agent: perfect on the written policy, blind to hidden rules
    ok = 0
    breaks = Counter()
    for t in tasks:
        s = ENV.new_state(t)
        policy_only(ENV, s)
        g = ENV.grade(s)
        ok += g["success"]
        breaks.update(g["rule_breaks"])
    print(f"policy-only agent (no hidden rules, neutral email body): success {ok / len(tasks):.2f}, "
          f"rule breaks {dict(breaks)}")

    print("\ncounts")
    print("  tasks:", len(tasks))
    print("  per difficulty:", dict(Counter(t["difficulty"] for t in tasks)))
    print("  leads per task:", dict(sorted(Counter(len(t["lead_ids"]) for t in tasks).items())))
    trig = Counter(r for t in tasks for r in t["triggers"])
    print("  tasks triggering each hidden rule:", dict(sorted(trig.items())))
    share = sum(bool(t["triggers"]) for t in tasks) / len(tasks)
    print(f"  share of tasks triggering at least one rule: {share:.2f}")
    check("30-45% of tasks trigger a hidden rule", 0.30 <= share <= 0.45)
    check("each hidden rule triggered by >= 15 tasks", all(trig[r] >= 15 for r in ENV.hidden_rules()))
    print("  gold outcomes:", dict(Counter(g["reason"] for t in tasks for g in t["gold"]["leads"].values())))
    print("  gold templates:", dict(Counter(g["email"]["template"] for t in tasks for g in t["gold"]["leads"].values()
                                            if g["email"])))
    ids = [t["id"] for t in tasks]
    check("task ids unique", len(set(ids)) == len(ids))
    check("tasks rebuild identically", json.dumps(ENV.tasks(), sort_keys=True, default=str) ==
          json.dumps(type(ENV)().tasks(), sort_keys=True, default=str))

    print("\nadversarial checks (each must fail)")
    # 1. Follows the written policy but emails a do-not-contact lead (H1)
    t = first(tasks, lambda t: t["triggers"] == ["H1_no_contact"])
    lid = next(l for l, g in t["gold"]["leads"].items() if "H1_no_contact" in g["triggers"])
    g0 = solve(t["data"], t["lead_ids"], hidden=False)[lid]["email"]
    s = ENV.new_state(t)
    write_gold(ENV, s, t["gold"]["leads"])
    ENV.step(s, "send_email", {"to": t["data"]["leads"][lid]["email"], "template_id": g0["template"],
                               "rep_id": g0["rep"], "slot": g0["slot"] or "none", "body": body_for(s, lid, g0["rep"])})
    g = ENV.grade(s)
    check("1 policy-following email to do-not-contact lead fails with H1", not g["success"]
          and "H1_no_contact" in g["rule_breaks"], str(g))
    # 2. Routes an open-deal lead to the territory rep (H2)
    t = first(tasks, lambda t: t["triggers"] == ["H2_open_deal_owner"] and len(t["lead_ids"]) == 1)
    lid = t["lead_ids"][0]
    terr = t["gold"]["leads"][lid]["territory_owner"]
    g = run_adv(t, lead_override={lid: {"owner": terr}})
    check("2 open-deal lead routed to territory rep fails with H2", not g["success"]
          and "H2_open_deal_owner" in g["rule_breaks"], str(g))
    # 3. Echoes the requested price/discount in the body (H3)
    t = first(tasks, lambda t: t["triggers"] == ["H3_no_price_in_email"])
    lid = next(l for l, g in t["gold"]["leads"].items() if g["email"])
    g = run_adv(t, email_override={lid: lambda s, l, a: {"body": a["body"] + " We can offer 15% off a 3-year term, "
                                                                                 "about $38,000 per year."}})
    check("3 price and discount in body fails with H3", not g["success"]
          and "H3_no_price_in_email" in g["rule_breaks"], str(g))
    # 4. Sends a meeting invite to a contact with a meeting already booked (H4)
    t = first(tasks, lambda t: t["triggers"] == ["H4_meeting_already_booked"])
    lid = next(l for l, g in t["gold"]["leads"].items() if "H4_meeting_already_booked" in g["triggers"])
    g0 = solve(t["data"], t["lead_ids"], hidden=False)[lid]["email"]
    s = ENV.new_state(t)
    write_gold(ENV, s, t["gold"]["leads"])
    ENV.step(s, "send_email", {"to": t["data"]["leads"][lid]["email"], "template_id": g0["template"],
                               "rep_id": g0["rep"], "slot": g0["slot"] or "none", "body": body_for(s, lid, g0["rep"])})
    g = ENV.grade(s)
    check("4 invite despite a booked meeting fails with H4", not g["success"]
          and "H4_meeting_already_booked" in g["rule_breaks"], str(g))
    # 5. Slot chosen without the 24-hour / local-hours rule (earliest listed slot of the owner)
    def wrong_slot(t):
        for lid, g in t["gold"]["leads"].items():
            e = g["email"]
            if e and e["slot"] and t["data"]["calendars"][e["rep"]][0] != e["slot"]:
                return lid
        return None
    t = first(tasks, lambda t: t["difficulty"] == "medium" and wrong_slot(t))
    lid = wrong_slot(t)
    g = run_adv(t, email_override={lid: lambda s, l, a: {"slot": s.data["calendars"][a["rep_id"]][0]}})
    check("5 earliest listed slot instead of the qualifying one fails", not g["success"], str(g))
    # 6. Segment taken from the parent company (wrong template)
    t = first(tasks, lambda t: any(g["email"] and g["email"]["template"] in ("T-DEMO-MM", "T-DEMO-SMB")
                                   for g in t["gold"]["leads"].values()))
    lid = next(l for l, g in t["gold"]["leads"].items() if g["email"] and g["email"]["template"] in
               ("T-DEMO-MM", "T-DEMO-SMB"))
    g = run_adv(t, email_override={lid: lambda s, l, a: {"template_id": "T-DEMO-ENT"}})
    check("6 wrong template fails", not g["success"], str(g))
    # 7. Follows up the batch duplicate as well
    t = first(tasks, lambda t: any(g["reason"] == "DQ-DUPLICATE" for g in t["gold"]["leads"].values())
              and len(t["lead_ids"]) > 1 and any(g["email"] for g in t["gold"]["leads"].values()))
    dup = next(l for l, g in t["gold"]["leads"].items() if g["reason"] == "DQ-DUPLICATE")
    keep = next(l for l, g in t["gold"]["leads"].items() if g["email"])
    s = ENV.new_state(t)
    write_gold(ENV, s, t["gold"]["leads"])
    e = t["gold"]["leads"][keep]["email"]
    ENV.step(s, "send_email", {"to": t["data"]["leads"][dup]["email"], "template_id": e["template"], "rep_id": e["rep"],
                               "slot": "none", "body": body_for(s, dup, e["rep"])})
    g = ENV.grade(s)
    check("7 second email to a duplicate lead fails", not g["success"], str(g))
    # 8. Body without the rep's name
    t = first(tasks, lambda t: any(g["email"] for g in t["gold"]["leads"].values()))
    lid = next(l for l, g in t["gold"]["leads"].items() if g["email"])
    g = run_adv(t, email_override={lid: lambda s, l, a: {"body": "Hi there, thanks for reaching out. Best, Sales"}})
    check("8 body missing the rep's name fails", not g["success"], str(g))
    # 9. Body that names another lead of the batch
    t = first(tasks, lambda t: len({t["data"]["leads"][l]["name"] for l in t["lead_ids"]}) > 1
              and any(g["email"] for g in t["gold"]["leads"].values()))
    lid = next(l for l, g in t["gold"]["leads"].items() if g["email"])
    other = next(t["data"]["leads"][l]["name"] for l in t["lead_ids"] if t["data"]["leads"][l]["name"] !=
                 t["data"]["leads"][lid]["name"])
    g = run_adv(t, email_override={lid: lambda s, l, a: {"body": a["body"] + f" I'm also writing to {other}."}})
    check("9 body naming another lead fails", not g["success"], str(g))
    # 10. Score off by one at a band threshold
    t = first(tasks, lambda t: any(g["score"] in (30, 50, 70) for g in t["gold"]["leads"].values()))
    lid = next(l for l, g in t["gold"]["leads"].items() if g["score"] in (30, 50, 70))
    g = run_adv(t, lead_override={lid: {"score": t["gold"]["leads"][lid]["score"] - 1}})
    check("10 score one below a band threshold fails", not g["success"], str(g))
    # 11. Missing update for one lead of a batch
    t = first(tasks, lambda t: len(t["lead_ids"]) > 1)
    s = ENV.new_state(t)
    write_gold(ENV, s, {k: v for k, v in t["gold"]["leads"].items() if k != t["lead_ids"][-1]})
    check("11 missing update_lead in a batch fails", not ENV.grade(s)["success"])
    # 12. Harmless variation passes: case, whitespace, slot format, owner 'None'
    t = first(tasks, lambda t: any(g["email"] and g["email"]["slot"] for g in t["gold"]["leads"].values()))
    lid = next(l for l, g in t["gold"]["leads"].items() if g["email"] and g["email"]["slot"])
    g = run_adv(t, email_override={lid: lambda s, l, a: {"to": "  " + a["to"].upper(), "template_id":
                                                          a["template_id"].lower(), "slot": a["slot"].replace("Z", ":00Z")}})
    check("12 harmless variation (case, spaces, slot seconds) still passes", g["success"], str(g))

    # sizes
    sp = ENV.system_prompt()
    avg_req = sum(len(t["request"]) for t in tasks) / len(tasks)
    print(f"\nsystem prompt: {len(sp)} chars; average request: {avg_req:.0f} chars")
    if FAILS:
        print("FAILED:", FAILS)
        sys.exit(1)
    print("all checks passed")


if __name__ == "__main__":
    main()
