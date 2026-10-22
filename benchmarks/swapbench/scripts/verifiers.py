"""Grade swap verifiers against hidden-set truth.

  python scripts/verifiers.py --incumbent <dir with train/ pool/ test/ results> --self-nextstep <json> \
      --candidate NAME=<dir>[,nextstep=<json>] ... [--margin 5]

A verifier is a procedure that returns SAFE / UNSAFE / INSUFFICIENT_EVIDENCE for a candidate:
  nextstep   next-step replay on the incumbent's visible traces (no tools executed, no user simulator):
             SAFE if the candidate's tool-call agreement with the incumbent is within `margin` of the
             incumbent's agreement with itself, else UNSAFE
  replay-60  full multi-turn replay on the 60 visible scenarios, paired 95% CI gate
  replay-260 the same on 260 scenarios (visible + fresh pool)
Truth: full replay on the 240 hidden scenarios (REGRESSED / NON-INFERIOR / AMBIGUOUS).
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from swapbench import stats, tau2_adapter  # noqa: E402


def load(d, split):
    p = os.path.join(d, split, "results.json")
    return tau2_adapter.load(p) if os.path.exists(p) else None


def gate(q, h, m):
    if q["lo"] > -m and not (h["delta"] > 0.01 and h["lo"] > 0):
        return "SAFE"
    if q["hi"] < -m or (h["lo"] is not None and h["lo"] > 0.01):
        return "UNSAFE"
    return "INSUFFICIENT_EVIDENCE"


def score(verdict, truth):
    if truth == "AMBIGUOUS":
        return "n/a (truth ambiguous)"
    if verdict == "SAFE":
        return "correct" if truth == "NON-INFERIOR" else "FALSE SAFE"
    if verdict == "UNSAFE":
        return "correct" if truth == "REGRESSED" else "false alarm"
    return "abstain"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--incumbent", required=True)
    ap.add_argument("--self-nextstep", required=True)
    ap.add_argument("--candidate", action="append", required=True)
    ap.add_argument("--margin", type=float, default=5.0)
    ap.add_argument("--md")
    a = ap.parse_args()
    m = a.margin / 100
    inc = {s: load(a.incumbent, s) for s in ("train", "pool", "test")}
    self_ns = json.load(open(a.self_nextstep))["summary"]
    lines = [f"Margin {a.margin:.0f} pts. Incumbent next-step self-agreement: tool calls "
             f"{self_ns['tool_exact']*100:.1f}%, all steps {self_ns['exact_all']*100:.1f}%.\n",
             "| candidate | truth: Δ on 240 hidden [95% CI] | truth | next-step tool agreement | nextstep verdict | "
             "replay-60 Δ [CI] | replay-60 verdict | replay-260 Δ [CI] | replay-260 verdict |",
             "|---|---|---|---|---|---|---|---|---|"]
    tally = {}
    for spec in a.candidate:
        name, rest = spec.split("=", 1)
        parts = rest.split(",")
        d = parts[0]
        ns_path = next((p.split("=", 1)[1] for p in parts[1:] if p.startswith("nextstep=")), None)
        c = {s: load(d, s) for s in ("train", "pool", "test")}
        qt, ht = stats.paired_delta(c["test"], inc["test"]), stats.paired_delta(c["test"], inc["test"], "harmful_writes")
        truth = stats.truth_label(qt, ht, m)
        row = [name, f"{qt['delta']*100:+.1f} [{qt['lo']*100:+.1f}, {qt['hi']*100:+.1f}]", truth]
        verdicts = {}
        if ns_path and os.path.exists(ns_path):
            ns = json.load(open(ns_path))["summary"]
            v = "SAFE" if ns["tool_exact"] >= self_ns["tool_exact"] - m else "UNSAFE"
            row += [f"{ns['tool_exact']*100:.1f}%", v]
            verdicts["nextstep"] = v
        else:
            row += ["(= incumbent)", "SAFE"]
            verdicts["nextstep"] = "SAFE"
        for label, splits in (("replay-60", ("train",)), ("replay-260", ("train", "pool"))):
            ce = [e for s in splits for e in (c[s] or [])]
            ie = [e for s in splits for e in (inc[s] or [])]
            q, h = stats.paired_delta(ce, ie), stats.paired_delta(ce, ie, "harmful_writes")
            v = gate(q, h, m) if q["n"] else "n/a"
            row += [f"{q['delta']*100:+.1f} [{q['lo']*100:+.1f}, {q['hi']*100:+.1f}] (n={q['n']})", v]
            verdicts[label] = v
        for k, v in verdicts.items():
            tally.setdefault(k, []).append(score(v, truth))
        lines.append("| " + " | ".join(row) + " |")
    lines.append("\n| verifier | " + " | ".join(n.split("=")[0] for n in a.candidate) + " |")
    lines.append("|---|" + "---|" * len(a.candidate))
    for k, v in tally.items():
        lines.append(f"| {k} | " + " | ".join(v) + " |")
    text = "\n".join(lines)
    print(text)
    if a.md:
        open(a.md, "w").write(text + "\n")


if __name__ == "__main__":
    main()
