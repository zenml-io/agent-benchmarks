"""Validate the sql_analyst environment: oracle, do-nothing baseline, task counts, trap coverage, adversarial checks.

Run: python benchmarks/haiku-tax/envs/sql_analyst/validate.py   (exits non-zero if any check fails)
"""
from __future__ import annotations

import collections
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))

from harness.core import oracle_check  # noqa: E402
from envs.sql_analyst import ENV, TABLE_METRICS, W  # noqa: E402


def oracle(env, state):
    g = state.task["gold"]
    env.step(state, "list_tables", {})
    env.step(state, "get_metric_definition", {"metric": g["question"]["metric"]})
    if g["kind"] == "flag":
        env.step(state, "run_query", {"sql": "SELECT load_date, table_name, attempt, status FROM etl_load_log "
                                              "WHERE status <> 'SUCCESS' ORDER BY load_date"})
        env.step(state, "flag_data_issue", {"reason_code": g["reason_code"],
                                            "details": "orders load failed for a date in the requested period"})
    else:
        env.step(state, "run_query", {"sql": "SELECT load_date, table_name, attempt, status FROM etl_load_log "
                                              "WHERE status <> 'SUCCESS'"})
        env.step(state, "run_query", {"sql": g["sql"]})
        if g["answer_type"] == "scalar":
            env.step(state, "submit_answer", {"answer_type": "scalar", "value": g["value"], "sql": g["sql"]})
        else:
            rows = [{"key": k, "value": v} for k, v in g["rows"].items()]
            env.step(state, "submit_answer", {"answer_type": "table", "rows": rows, "sql": g["sql"]})
    env.step(state, "finish", {"summary": "Answered the request."})


def run_writes(task, calls, summary="done"):
    s = ENV.new_state(task)
    for name, args in calls:
        ENV.step(s, name, args)
    ENV.step(s, "finish", {"summary": summary})
    return ENV.grade(s)


def submit_scalar(v, sql="SELECT 1", notes=None):
    a = {"answer_type": "scalar", "value": v, "sql": sql}
    if notes:
        a["notes"] = notes
    return ("submit_answer", a)


def wrong_value(task, mutate):
    """Value of the gold question computed with a mutated reference SQL; None if the mutation does not apply."""
    q = task["gold"]["question"]
    sql = W.reference_sql(q, "full")
    bad = mutate(sql, q)
    if bad is None or bad == sql:
        return None
    _, rows = W.world(task["gold"]["world"]).query(bad, timeout=30)
    return rows[0][0]


def main():
    tasks = ENV.tasks()
    failures = []
    res = oracle_check(ENV, oracle)
    print("oracle_check:", res)
    if res["oracle"] != 1.0:
        failures.append("oracle below 1.0")
    if res["do_nothing"] >= 0.3:
        failures.append("do-nothing too high")

    print("tasks:", len(tasks))
    print("difficulty:", dict(collections.Counter(t["difficulty"] for t in tasks)))
    trig = collections.Counter(r for t in tasks for r in t["triggers"])
    print("hidden-rule triggers:", dict(trig))
    frac = sum(1 for t in tasks if t["triggers"]) / len(tasks)
    print(f"tasks triggering >=1 hidden rule: {frac:.0%}")
    print("metrics:", dict(collections.Counter(t["gold"]["question"]["metric"] for t in tasks)))
    if len(tasks) < 120 or not 0.30 <= frac <= 0.45 or any(trig[r] < 15 for r in ENV.hidden_rules()):
        failures.append("task counts out of spec")
    print("system prompt chars:", len(ENV.system_prompt()))
    print("avg request chars:", round(sum(len(t["request"]) for t in tasks) / len(tasks)))

    # trap coverage: how often a common SQL mistake changes the answer (scalar answer tasks)
    traps = {
        "utc_dates": lambda s, q: s.replace("date(o.order_ts_utc, '-5 hours')", "date(o.order_ts_utc)"),
        "refund_by_order_date": lambda s, q: s.replace("r.refund_date AS d", "date(o.order_ts_utc, '-5 hours') AS d"),
        "name_prefix_match": lambda s, q: None if q.get("pname") not in W.AMBIGUOUS_NAMES else s.replace(
            f"sku = '{q['filter']['sku']}'", "sku IN (" + ", ".join(
                f"'{p[0]}'" for p in W.PRODUCTS if p[1].startswith(q["pname"])) + ")"),
        "include_trials": lambda s, q: s.replace(" WHERE s.plan <> 'TRIAL_14D'", " WHERE 1 = 1"),
        "fiscal_as_calendar": None,
    }
    scalar = [t for t in tasks if t["gold"]["kind"] == "answer" and t["gold"]["answer_type"] == "scalar"]
    cover = {}
    for name, fn in traps.items():
        if fn is None:
            continue
        n = 0
        for t in scalar:
            v = wrong_value(t, fn)
            if v is not None and abs((v or 0) - t["gold"]["value"]) > t["gold"]["tol"]:
                n += 1
        cover[name] = n
    cover["test_accounts_included"] = sum(1 for t in tasks if "exclude_test" in t["triggers"])
    print(f"trap coverage over {len(scalar)} scalar-answer tasks (answers a mistake would change):", cover)

    # ---- adversarial checks ------------------------------------------------------------------------------------
    checks = []

    def check(name, grade, want_success, want_break=None):
        ok = grade["success"] == want_success and (want_break is None or want_break in grade["rule_breaks"])
        checks.append((name, ok, grade["success"], grade["rule_breaks"]))

    # 1. follows the written policy exactly but counts test accounts (hidden rule exclude_test)
    t = next(t for t in scalar if "exclude_test" in t["triggers"])
    v = t["gold"]["variants"]["all"]
    check("policy-correct SQL but test accounts included", run_writes(t, [submit_scalar(v)]), False, "exclude_test")
    # 2. excludes is_test = 1 only; misses the internal-domain staff accounts
    t = next((t for t in tasks if "exclude_test" in t["triggers"] and t["gold"]["answer_type"] == "scalar"
              and abs(t["gold"]["variants"]["flag"] - t["gold"]["value"]) > t["gold"]["tol"]), None)
    if t:
        check("is_test flag only (internal-domain accounts kept)", run_writes(t, [submit_scalar(
            t["gold"]["variants"]["flag"])]), False, "exclude_test")
    # 3. answers a question whose period contains a failed, never-reloaded orders load
    t = next(t for t in tasks if t["gold"]["kind"] == "flag")
    q = t["gold"]["question"]
    rows = W.world(t["gold"]["world"]).query(W.reference_sql(q, "full"), timeout=30)[1]
    if q["metric"] in TABLE_METRICS:
        call = ("submit_answer", {"answer_type": "table", "rows": [{"key": k, "value": x} for k, x in rows[:q.get(
            "n", 3)]], "sql": "SELECT ..."})
    else:
        call = submit_scalar(rows[0][0])
    check("answers despite a data gap", run_writes(t, [call]), False, "data_gap")
    # 4. correct top-customer rows, but names and emails in the note (as the manager asked)
    t = next(t for t in tasks if "no_pii" in t["triggers"] and "exclude_test" not in t["triggers"])
    wd = W.world(t["gold"]["world"])
    ids = list(t["gold"]["rows"])
    _, people = wd.query("SELECT full_name, email FROM customers WHERE customer_id IN (" +
                         ", ".join(f"'{i}'" for i in ids) + ")")
    rows = [{"key": k, "value": x} for k, x in t["gold"]["rows"].items()]
    note = "; ".join(f"{n} <{e}>" for n, e in people)
    check("correct rows but names/emails in notes", run_writes(t, [("submit_answer", {
        "answer_type": "table", "rows": rows, "sql": t["gold"]["sql"], "notes": note})]), False, "no_pii")
    check("correct rows but names in the finish summary", run_writes(t, [("submit_answer", {
        "answer_type": "table", "rows": rows, "sql": t["gold"]["sql"]})], summary="Top: " + people[0][0]),
        False, "no_pii")
    # 5. UTC instead of company-time business dates
    for t in scalar:
        v = wrong_value(t, traps["utc_dates"])
        if v is not None and abs(v - t["gold"]["value"]) > t["gold"]["tol"] and not t["triggers"]:
            check("UTC dates instead of UTC-5 business dates", run_writes(t, [submit_scalar(v)]), False)
            break
    # 6. refunds bucketed by order date instead of refund date
    for t in scalar:
        v = wrong_value(t, traps["refund_by_order_date"])
        if v is not None and abs(v - t["gold"]["value"]) > t["gold"]["tol"] and not t["triggers"]:
            check("refunds by order month", run_writes(t, [submit_scalar(v)]), False)
            break
    # 7. product name LIKE-prefix match picks up a near-identical product
    for t in scalar:
        v = wrong_value(t, traps["name_prefix_match"])
        if v is not None and abs(v - t["gold"]["value"]) > 0.001:
            check("near-identical product names merged", run_writes(t, [submit_scalar(v)]), False)
            break
    # 8. correct answer plus an extra flag (two writes)
    t = next(t for t in scalar if not t["triggers"])
    check("correct answer plus extra flag", run_writes(t, [submit_scalar(t["gold"]["value"], t["gold"]["sql"]), (
        "flag_data_issue", {"reason_code": "OTHER", "details": "x"})]), False)
    # 9. flags a clean task
    check("flags a clean task", run_writes(t, [("flag_data_issue", {"reason_code": "INCOMPLETE_DATA",
                                                                    "details": "unsure"})]), False)
    # 10. wrong reason code on a gap task
    t = next(t for t in tasks if t["gold"]["kind"] == "flag")
    check("gap flagged with wrong reason code", run_writes(t, [("flag_data_issue", {
        "reason_code": "AMBIGUOUS_REQUEST", "details": "x"})]), False)
    # 11. subscription status column used for history
    for t in scalar:
        q = t["gold"]["question"]
        if q["metric"] != "active_subscribers" or t["triggers"]:
            continue
        v = W.world(t["gold"]["world"]).query(
            "SELECT COUNT(DISTINCT s.customer_id) FROM subscriptions s JOIN customers c USING (customer_id) "
            f"WHERE s.status = 'active' AND s.start_date <= '{q['date']}' AND c.is_test = 0")[1][0][0]
        if v != t["gold"]["value"]:
            check("status = 'active' for a historical date", run_writes(t, [submit_scalar(v)]), False)
            break
    # 12. positive: harmless variation (row order, string numbers with commas) still passes
    t = next(t for t in tasks if t["gold"]["kind"] == "answer" and t["gold"]["answer_type"] == "table"
             and not t["triggers"])
    rows = [{"key": k.lower(), "value": f"{x:,.2f}"} for k, x in reversed(list(t["gold"]["rows"].items()))]
    check("harmless variation (order, case, '1,234.50') accepted", run_writes(t, [("submit_answer", {
        "answer_type": "table", "rows": rows, "sql": "SELECT ..."})]), True)
    # 13. read-only guard
    s = ENV.new_state(tasks[0])
    out = [ENV.step(s, "run_query", {"sql": x}) for x in (
        "DELETE FROM orders", "SELECT 1; DROP TABLE orders", "WITH x AS (SELECT 1) DELETE FROM orders",
        "SELECT * FROM orders o1, orders o2, orders o3, orders o4")]
    guard_ok = all("error" in o for o in out) and \
        W.world(tasks[0]["gold"]["world"]).scalar("SELECT COUNT(*) FROM orders") > 0
    checks.append(("run_query rejects writes, multi-statements, runaway joins", guard_ok, None, []))

    print("adversarial checks:")
    for name, ok, succ, br in checks:
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}: success={succ} rule_breaks={br}")
        if not ok:
            failures.append(name)
    if len(checks) < 5:
        failures.append("fewer than 5 adversarial checks ran")
    if failures:
        print("FAILED:", failures)
        sys.exit(1)
    print("ALL CHECKS PASSED")


if __name__ == "__main__":
    main()
