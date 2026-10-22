"""Solve every task from the rebuilt environment and check the answer against Snorkel's reference answer.

  python env/oracle.py env/extracted.json env/insurance.db env/tasks.json

A task is kept (written to env/tasks.json) only when the rules in env/guidelines.txt, applied to the rebuilt tables
and the company's NAICS code, reproduce its reference answer exactly. That validates both the environment and the
NAICS code recovered for the company; tasks that do not reproduce are reported with the reason.
"""
import json
import re
import sqlite3
import sys
from collections import Counter

CONSTRUCTION_TYPE = {  # building_construction_types.json in Snorkel's environment, as printed in the traces
    "Non-Combustible Fire-Resistive": "Type I", "Non-combustible –": "Type II", "Hybrid Non-Combustible": "Type III",
    "Heavy Timber": "Type IV", "Wood Frame": "Type V"}
CYBER_HIGH = ("517", "518", "52", "621", "622310", "623", "92")
AUTO_HIGH = ("484", "4853", "4854", "4855", "4871")
LOBS = ["workers compensation", "property", "general liability", "auto", "cyber", "bop"]
ABBR = None


def construction_type(text):
    return next((t for k, t in CONSTRUCTION_TYPE.items() if text.startswith(k)), None)


def small_business(db, naics, company):
    """True/False, or None when the size standard cannot be resolved."""
    c2017 = [r[0] for r in db.execute('SELECT "2017 NAICS" FROM naics_2022_2017 WHERE "2022 NAICS"=?', (naics,))]
    c2012 = {r[0] for c in c2017 for r in db.execute('SELECT "2012 NAICS" FROM naics_2012_2017 WHERE "2017 NAICS"=?',
                                                       (c,))}
    verdicts = set()
    for code in c2012:
        for dollars, employees in db.execute(
                'SELECT "Size Standards in millions of dollars", "Size standards in number of employees" '
                'FROM small_business_definition WHERE "NAICS Codes"=?', (code,)):
            if dollars is not None:
                verdicts.add(company["annual revenue"] <= dollars * 1e6)
            elif employees is not None:
                verdicts.add(company["number of employees"] <= employees)
    return verdicts.pop() if len(verdicts) == 1 else None


def appetite(db, naics, company, lob):
    """'yes' | 'no' | None (unresolved)."""
    small = small_business(db, naics, company)
    if small is None:
        return None
    if not small:
        return "no"
    row = db.execute("SELECT appetite FROM appetite_guide WHERE naics=? AND state=? AND lob=?",
                     (naics, ABBR[company["state"]], lob)).fetchone()
    if row is None:
        return None
    v = row[0].lower()
    if v != "qualified":
        return v
    if lob == "property":
        return "yes" if construction_type(company["building construction"]) in ("Type I", "Type II") else "no"
    if lob == "auto":
        return "no" if company["number of vehicles"] > 20 else "yes"
    if lob == "workers compensation":
        return "no" if company["total payroll"] > 5_000_000 else "yes"
    return None


def solve(db, t):
    """The canonical answer for a task, or None when the environment cannot resolve it."""
    c, lob, n = t["company"], t["company"]["lob"], t["naics"]
    kind = t["task"]
    if kind == "Business Classification":
        return ("naics", n)
    if n is None:
        return None
    if kind.startswith("Small Business"):
        s = small_business(db, n, c)
        return None if s is None else ("small", s)
    a = appetite(db, n, c, lob)
    if a is None:
        return None
    if kind == "Appetite Check":
        return ("appetite", a)
    if kind == "Product Recommendations":
        others = [appetite(db, n, c, other) for other in LOBS if other != lob]
        if None in others:
            return None
        return ("products", frozenset(o for o, v in zip([x for x in LOBS if x != lob], others) if v == "yes"))
    if a == "no":
        return ("out_of_appetite", True)
    if kind == "Policy Limits":
        high = lob == "cyber" and str(n).startswith(CYBER_HIGH)
        return ("limits", (3.0, 5.0) if high else (1.0, 2.0))
    if kind == "Deductibles":
        if lob == "auto":
            return ("deductible", 5000.0 if str(n).startswith(AUTO_HIGH) else 1000.0)
        return ("deductible", 500.0)
    return None


def parse_reference(t):
    r = t["reference"]
    if m := re.search(r"NAICS code is (\d{6})", r):
        return ("naics", int(m[1]))
    if re.search(r"qualif(y|ies) as a small business", r):
        return ("small", "NOT" not in r)
    if "appetite for that company and LOB is qualified" in r:
        return ("unsupported", "qualified appetite (later environment version)")
    if re.search(r"not (appear to be )?in appetite", r) and t["task"] in ("Policy Limits", "Deductibles"):
        return ("out_of_appetite", True)
    if t["task"] == "Appetite Check":
        if r.startswith("Yes"):
            return ("appetite", "yes")
        if r.startswith("No"):
            return ("appetite", "no")
    if m := re.search(r"per-incident policy limit of \$([\d.]+) million and an aggregate limit of \$([\d.]+) million", r):
        return ("limits", (float(m[1]), float(m[2])))
    if m := re.search(r"\$([\d.]+) deductible", r):
        return ("deductible", float(m[1]))
    if t["task"] == "Product Recommendations":
        if "qualified" in r:
            return ("unsupported", "qualified LOBs (later environment version)")
        if r.startswith("No other LOBs"):
            return ("products", frozenset())
        if m := re.search(r"LOBs in appetite for this company are (.+?)\.?$", r):
            return ("products", frozenset(x.strip() for x in m[1].split(",")))
    return ("unparsed", r)


def main(extracted, db_path, out):
    global ABBR
    ex = json.load(open(extracted))
    db = sqlite3.connect(db_path)
    ABBR = dict(db.execute("SELECT State, Abbreviation FROM states"))
    kept, why = [], Counter()
    by_type = Counter()
    for t in ex["tasks"]:
        ref = parse_reference(t)
        got = solve(db, t)
        if ref[0] in ("unparsed", "unsupported"):
            why[f"{t['source']}: reference {ref[0]}"] += 1
        elif t["naics"] is None:
            why[f"{t['source']}: company NAICS unknown"] += 1
        elif got is None:
            why[f"{t['source']}: environment cannot resolve"] += 1
        elif got != ref:
            why[f"{t['source']}: oracle disagrees"] += 1
        else:
            kept.append({**t, "gold": [ref[0], sorted(ref[1]) if isinstance(ref[1], frozenset) else ref[1]]})
            by_type[(t["source"], t["task"])] += 1
    json.dump(kept, open(out, "w"), indent=1)
    print(f"kept {len(kept)} of {len(ex['tasks'])}")
    for k, v in sorted(by_type.items()):
        print("  kept", k, v)
    for k, v in why.most_common():
        print("  dropped", k, v)


if __name__ == "__main__":
    main(*sys.argv[1:4])
