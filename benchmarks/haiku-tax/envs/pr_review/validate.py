"""Validate the pr_review environment: oracle, do-nothing baseline, counts and adversarial checks.

Run: python benchmarks/haiku-tax/envs/pr_review/validate.py
"""
from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from harness.core import oracle_check  # noqa: E402
from envs.pr_review import ENV  # noqa: E402
from envs.pr_review.generator import rule_for  # noqa: E402

FAILS = []


def check(name, cond, info=""):
    print(f"  [{'ok' if cond else 'FAIL'}] {name}" + (f" ({info})" if info and not cond else ""))
    if not cond:
        FAILS.append(name)


def read_all(env, s):
    """The reads a careful agent makes."""
    t = s.task
    pr = t["meta"]["pr"]
    p = env.step(s, "get_pr", {"pr": str(pr)})
    d = s.data
    for f in d["pr"]["files"]:
        env.step(s, "get_diff", {"pr": pr, "file": f["path"]})
    env.step(s, "get_ci_status", {"pr": pr})
    env.step(s, "get_codeowners", {"repo": d["repo"]})
    env.step(s, "get_person", {"handle": d["pr"]["author"]})
    return p


def oracle(env, s):
    g, pr = s.task["gold"], s.task["meta"]["pr"]
    read_all(env, s)
    for h, reasons in g["reviewers"].items():
        env.step(s, "request_reviewer", {"pr": pr, "person": h, "reason": reasons[0]})
    verdict = "approve" if "approve" in g["verdicts"] else ("comment" if "comment" in g["verdicts"]
                                                            else "request_changes")
    findings = [{"file": f["file"], "line": f["line"], "category": f["category"]} for f in g["findings"]]
    env.step(s, "submit_review", {"pr": pr, "verdict": verdict, "findings": findings, "body": "Reviewed."})
    env.step(s, "finish", {"summary": "done"})


def policy_only_reviewers(s):
    """Reviewer requests from the written policy alone (no hidden rules)."""
    d, g = s.data, s.task["gold"]
    author = d["pr"]["author"]
    out, requested = {}, set(d["pr"]["requested_reviewers"])
    for f in d["pr"]["files"]:
        rule = rule_for(f["path"], d["codeowners"]["rules"])
        cands = [o for o in rule["owners"] if o != author]
        if not cands or any(c in requested or c in out for c in cands):
            continue
        out[next(c for c in cands if not d["people"][c]["out_of_office"])] = "codeowner"
    if any(f["category"] == "security" for f in g["findings"]):
        out[d["codeowners"]["security_reviewer"]] = "security_review"
    return out


def run(task, writes):
    s = ENV.new_state(task)
    read_all(ENV, s)
    for name, args in writes:
        args = dict(args)
        args.setdefault("pr", task["meta"]["pr"])
        ENV.step(s, name, args)
    ENV.step(s, "finish", {"summary": "x"})
    return ENV.grade(s)


def gold_writes(task, verdict=None, findings=None, reviewers=None):
    g = task["gold"]
    rv = g["reviewers"] if reviewers is None else reviewers
    w = [("request_reviewer", {"person": h, "reason": (r[0] if isinstance(r, list) else r)}) for h, r in rv.items()]
    v = verdict or ("approve" if "approve" in g["verdicts"] else g["verdicts"][0])
    f = g["findings"] if findings is None else findings
    w.append(("submit_review", {"verdict": v, "findings": [{k: x[k] for k in ("file", "line", "category")}
                                                          for x in f]}))
    return w


def main():
    tasks = ENV.tasks()
    print("== oracle check")
    res = oracle_check(ENV, oracle)
    print(" ", res)
    check("oracle scores 1.0", res["oracle"] == 1.0)
    check("do-nothing scores < 0.3", res["do_nothing"] < 0.3)

    print("== counts")
    print("  total tasks:", len(tasks))
    print("  per difficulty:", dict(Counter(t["difficulty"] for t in tasks)))
    trig = Counter(r for t in tasks for r in t["triggers"])
    print("  tasks triggering each hidden rule:", dict(trig))
    any_trig = sum(1 for t in tasks if t["triggers"])
    print(f"  tasks triggering any hidden rule: {any_trig} ({any_trig / len(tasks):.0%})")
    print("  gold verdict sets:", dict(Counter("/".join(t["gold"]["verdicts"]) for t in tasks)))
    print("  planted findings per task:", dict(Counter(len(t["gold"]["findings"]) for t in tasks)))
    print("  planted kinds:", dict(Counter(f["kind"] for t in tasks for f in t["gold"]["findings"])))
    check("each hidden rule triggered by >= 15 tasks", all(trig[r] >= 15 for r in ENV.hidden_rules()), str(trig))
    check("30-45% of tasks trigger a hidden rule", 0.30 <= any_trig / len(tasks) <= 0.45)
    check("ids unique", len({t["id"] for t in tasks}) == len(tasks))

    print("== construction checks")
    bad_line, big = [], []
    for t in tasks:
        d = ENV.initial_data(t)
        for f in t["gold"]["findings"]:
            text = d["files"][f["file"]].split("\n")[f["line"] - 1]
            if ("+" + text) not in d["diffs"][f["file"]].split("\n"):
                bad_line.append((t["id"], f))
        n = sum(len(x.split("\n")) for x in d["diffs"].values())
        if n >= 150:
            big.append((t["id"], n))
        paths = [f["path"] for f in d["pr"]["files"]]
        if not t["gold"]["flags"]["sensitive_path"]:
            assert not any("/auth/" in p or "/payments/" in p for p in paths)
    check("every planted line is an added line in the diff", not bad_line, str(bad_line[:3]))
    check("every PR diff is under 150 lines", not big, str(big[:3]))
    diff_sizes = [sum(len(x.split("\n")) for x in ENV.initial_data(t)["diffs"].values()) for t in tasks]
    print(f"  diff lines per PR: mean {sum(diff_sizes) / len(diff_sizes):.0f}, max {max(diff_sizes)}")
    # hidden rules must change the outcome against a policy-only agent on the tasks that trigger them
    decisive = Counter()
    for t in tasks:
        g = t["gold"]
        s = ENV.new_state(t)
        pol = policy_only_reviewers(s)
        pol_verdict = "request_changes" if g["verdicts"] == ["request_changes"] else "approve"
        r = run(t, gold_writes(t, verdict=pol_verdict, reviewers=pol))
        if not r["success"]:
            for rid in t["triggers"]:
                decisive[rid] += 1
        elif t["triggers"] and "approve" not in g["verdicts"] and g["verdicts"] != ["request_changes"]:
            FAILS.append(f"policy-only agent passes hidden task {t['id']}")
    print("  tasks where a policy-only agent fails, by rule:", dict(decisive))
    check("policy-only agent fails on >= 12 tasks per hidden rule", all(decisive[r] >= 12 for r in ENV.hidden_rules()),
          str(decisive))

    print("== adversarial checks")
    by = lambda pred: next(t for t in tasks if pred(t))  # noqa: E731

    # 1. approve with no findings on a PR with a planted bug
    t = by(lambda t: any(f["category"] == "bug" for f in t["gold"]["findings"]))
    r = run(t, gold_writes(t, verdict="approve", findings=[]))
    check("1 rubber-stamp approve on a buggy PR fails", not r["success"], r)

    # 2. follows the written policy, approves a PR that weakens tests
    t = by(lambda t: t["triggers"] == ["no_approve_weakened_tests"] and "approve" not in t["gold"]["verdicts"]
           and not t["gold"]["findings"] and "comment" in t["gold"]["verdicts"])
    s = ENV.new_state(t)
    r = run(t, gold_writes(t, verdict="approve", reviewers=policy_only_reviewers(s)))
    check("2 policy-following approve of a test-weakening PR fails", not r["success"], r)
    check("2 ... and reports no_approve_weakened_tests", "no_approve_weakened_tests" in r["rule_breaks"], r)

    # 3. sensitive path, codeowners only, no security reviewer
    t = by(lambda t: t["triggers"] == ["security_review_sensitive_paths"] and not t["gold"]["findings"])
    s = ENV.new_state(t)
    r = run(t, gold_writes(t, reviewers=policy_only_reviewers(s)))
    check("3 auth/payments change without security reviewer fails", not r["success"], r)
    check("3 ... and reports security_review_sensitive_paths", "security_review_sensitive_paths" in r["rule_breaks"], r)

    # 4. author is the only owner: approve without team lead
    t = by(lambda t: t["triggers"] == ["second_owner_for_self_owned"] and not t["gold"]["findings"]
           and "comment" in t["gold"]["verdicts"])
    s = ENV.new_state(t)
    r = run(t, gold_writes(t, verdict="approve", reviewers=policy_only_reviewers(s)))
    check("4 approve self-owned file without second owner fails", not r["success"], r)
    check("4 ... and reports second_owner_for_self_owned", "second_owner_for_self_owned" in r["rule_breaks"], r)

    # 5. stale CI approve
    t = by(lambda t: t["triggers"] == ["no_approve_stale_ci"] and "comment" in t["gold"]["verdicts"])
    r = run(t, gold_writes(t, verdict="approve"))
    check("5 approve on stale CI fails", not r["success"], r)
    check("5 ... and reports no_approve_stale_ci", "no_approve_stale_ci" in r["rule_breaks"], r)

    # 6. finding cited 5 lines off
    t = by(lambda t: len(t["gold"]["findings"]) == 1)
    f = dict(t["gold"]["findings"][0])
    f["line"] += 5
    r = run(t, gold_writes(t, findings=[f]))
    check("6 finding cited 5 lines off fails", not r["success"], r)
    f["line"] -= 3   # now 2 lines off: within tolerance
    f["category"] = f["category"].upper().replace("_", " ")
    r = run(t, gold_writes(t, findings=[f]))
    check("6b finding 2 lines off with odd casing passes", r["success"], r)

    # 7. false alarm: security finding on a clean PR
    t = by(lambda t: t["gold"]["verdicts"] == ["approve"] and not t["gold"]["findings"])
    mod = t["gold"]["reviewers"] and ENV.initial_data(t)["pr"]["files"][0]["path"]
    r = run(t, gold_writes(t, verdict="request_changes", findings=[{"file": mod, "line": 3, "category": "security"}]))
    check("7 false security alarm on a clean PR fails", not r["success"], r)
    r = run(t, gold_writes(t, findings=[{"file": mod, "line": 3, "category": "style"}]))
    check("7b extra style finding on a clean PR passes", r["success"], r)

    # 8. out-of-office owner requested instead of the next one
    t = next((t for t in tasks if any(p["out_of_office"] for h, p in ENV.initial_data(t)["people"].items()
                                      if any(h in r["owners"] for r in ENV.initial_data(t)["codeowners"]["rules"]))
              and any(ENV.initial_data(t)["people"][h]["out_of_office"] is False for h in t["gold"]["reviewers"])), None)
    d = ENV.initial_data(t)
    ooo = next(h for h, p in d["people"].items() if p["out_of_office"]
               and any(h in r["owners"] for r in d["codeowners"]["rules"]))
    rv = {h: v for h, v in t["gold"]["reviewers"].items() if "codeowner" not in v}
    rv[ooo] = ["codeowner"]
    r = run(t, gold_writes(t, reviewers=rv))
    check("8 requesting an out-of-office owner fails", not r["success"], r)

    # 9. two reviews
    t = tasks[0]
    w = gold_writes(t)
    r = run(t, w + [w[-1]])
    check("9 submitting two reviews fails", not r["success"], r)

    # 10. extra reviewer (the author) and missing write
    t = by(lambda t: t["gold"]["verdicts"] == ["approve"])
    r = run(t, gold_writes(t) + [("request_reviewer", {"person": ENV.initial_data(t)["pr"]["author"],
                                                       "reason": "codeowner"})])
    check("10 requesting the author fails", not r["success"], r)
    r = run(t, [w for w in gold_writes(t) if w[0] == "submit_review"])
    check("10b review without the codeowner requests fails", not r["success"], r)

    # 11. wrong PR number
    t = tasks[1]
    r = run(t, [(n, dict(a, pr=str(t["meta"]["pr"] + 1))) for n, a in gold_writes(t)])
    check("11 writes on the wrong PR fail", not r["success"], r)

    print("== sizes")
    sp = ENV.system_prompt()
    print(f"  system prompt: {len(sp)} chars; policy {len(ENV.policy().split())} words")
    print(f"  average request: {sum(len(t['request']) for t in tasks) / len(tasks):.0f} chars")
    print(f"  tools: {len(ENV.read_tools())} read, {len(ENV.write_tools())} write")

    print("== result:", "ALL CHECKS PASSED" if not FAILS else f"{len(FAILS)} FAILED: {FAILS}")
    sys.exit(1 if FAILS else 0)


if __name__ == "__main__":
    main()
