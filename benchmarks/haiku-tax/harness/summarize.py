"""Summarize result files: one line per use case x model x arm.

  python harness/summarize.py <results-dir> [--csv out.csv]

Uses the last record per task (a re-run after an API error replaces the earlier record). Tasks that ended in an
API error or a blocked account are excluded from success and counted separately; every other failure (empty reply,
tool-call parse error, step limit, refusal, no tool use) counts as unresolved.
"""
import argparse
import csv
import glob
import json
import os
import statistics as st

INFRA = ("api_error", "account_blocked", "timeout")


def load(path):
    last = {}
    for l in open(path):
        r = json.loads(l)
        last[r["task"]] = r
    return list(last.values())


def pct(xs, q):
    xs = sorted(xs)
    return xs[min(int(q * len(xs)), len(xs) - 1)] if xs else float("nan")


def summarize(rows):
    ok = [r for r in rows if r["status"] not in INFRA]
    n = len(ok)
    succ = sum(r["success"] for r in ok)
    cost = sum(r["cost"] for r in ok)
    trig = [r for r in ok if r.get("triggers")]
    fails = {}
    for r in ok:
        for f in r["failures"]:
            fails[f] = fails.get(f, 0) + 1
    return dict(n=n, infra=len(rows) - n, success=succ / n if n else float("nan"),
                rule_break=sum(bool(r["rule_breaks"]) for r in ok) / n if n else float("nan"),
                rule_break_trig=sum(bool(r["rule_breaks"]) for r in trig) / len(trig) if trig else float("nan"),
                cost=cost, cost_per_task=cost / n if n else float("nan"),
                cost_per_success=cost / succ if succ else float("inf"),
                p50=pct([r["latency"] for r in ok], 0.5), p95=pct([r["latency"] for r in ok], 0.95),
                steps=st.mean(r["steps"] for r in ok) if ok else 0, failures=fails,
                blocks=sum(sum(c.get("blocked", False) for c in r.get("checks", [])) for r in ok))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("root")
    ap.add_argument("--csv")
    a = ap.parse_args()
    out = []
    for p in sorted(glob.glob(os.path.join(a.root, "*", "*.jsonl"))):
        uc = os.path.basename(os.path.dirname(p))
        model, arm = os.path.basename(p)[:-6].split("__")
        s = summarize(load(p))
        out.append(dict(use_case=uc, model=model, arm=arm, **s))
        print(f"{uc:20s} {model:28s} {arm:4s} n={s['n']:3d} infra={s['infra']} success={s['success']:.0%} "
              f"breaks={s['rule_break']:.0%} (on trigger tasks {s['rule_break_trig']:.0%}) "
              f"$/task={s['cost_per_task'] * 100:.3f}c $/success={s['cost_per_success'] * 100:.3f}c "
              f"p50={s['p50']:.0f}s p95={s['p95']:.0f}s steps={s['steps']:.1f} fails={s['failures']}")
    if a.csv:
        with open(a.csv, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=[k for k in out[0] if k != "failures"] + ["failures"])
            w.writeheader()
            for r in out:
                w.writerow({**r, "failures": json.dumps(r["failures"])})


if __name__ == "__main__":
    main()
