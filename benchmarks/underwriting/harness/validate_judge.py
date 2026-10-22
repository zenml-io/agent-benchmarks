"""Check candidate judges against Snorkel's own correct/incorrect labels before using one to grade runs.

  <python with pandas> harness/validate_judge.py data_raw --n 300 --judges gpt-6.1-sol,haiku-5.5,gpt-6-luna

Samples labeled traces from both datasets (fixed seed, stratified by label), takes each trace's final answer, and
reports each judge's agreement and Cohen's kappa with the labels. Writes results/judge_validation.json.
"""
import argparse
import json
import os
import random
import sys
from concurrent.futures import ThreadPoolExecutor

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from judge import grade  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def final_answer(trace):
    """The assistant's last message containing FINAL ANSWER, else None. About a quarter of the code-gen traces
    have none (some end with the simulated underwriter stating the conclusion), so their labels do not measure a
    judge of final answers and they are left out."""
    texts = [str(s.get("content") or "") for s in trace if s.get("role") == "assistant"]
    for t in reversed(texts):
        if "FINAL ANSWER" in t.upper():
            return t[t.upper().index("FINAL ANSWER"):]
    return None


def kappa(pairs):
    n = len(pairs)
    po = sum(a == b for a, b in pairs) / n
    pa, pb = sum(a for a, _ in pairs) / n, sum(b for _, b in pairs) / n
    pe = pa * pb + (1 - pa) * (1 - pb)
    return (po - pe) / (1 - pe) if pe < 1 else 1.0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("raw")
    ap.add_argument("--n", type=int, default=300)
    ap.add_argument("--judges", default="gpt-6.1-sol,haiku-5.5,gpt-6-luna")
    a = ap.parse_args()
    rows = []
    for p in [f"{a.raw}/data/train-00000-of-00001.parquet", f"{a.raw}/codegen/train.parquet"]:
        for _, r in pd.read_parquet(p).iterrows():
            rows.append(dict(task=r["task"], reference=r["reference answer"], label=bool(r["correct"]),
                             answer=final_answer(r["trace"]), model=r["assistant model name"]))
    rows = [r for r in rows if r["answer"]]
    rng = random.Random(7)
    pos = [r for r in rows if r["label"]]
    neg = [r for r in rows if not r["label"]]
    k = min(a.n // 2, len(pos), len(neg))
    print(f"traces with a final answer: {len(pos)} labeled correct, {len(neg)} incorrect; sampling {k} of each")
    sample = rng.sample(pos, k) + rng.sample(neg, k)
    out = {}
    for j in a.judges.split(","):
        with ThreadPoolExecutor(16) as ex:
            res = list(ex.map(lambda r: grade(j, r["task"], r["reference"], r["answer"]), sample))
        got = [(r["label"], g[0]) for r, g in zip(sample, res) if g[0] is not None]
        cost = sum(g[2] for g in res)
        disagree = [dict(task=r["task"], label=r["label"], judge=g[0], reason=g[1], reference=r["reference"][:200],
                         answer=r["answer"][-400:]) for r, g in zip(sample, res) if g[0] is not None and g[0] != r["label"]]
        out[j] = dict(n=len(got), unparsed=len(res) - len(got),
                      agreement=sum(x == y for x, y in got) / len(got), kappa=kappa(got), cost=cost,
                      false_pass=sum(1 for x, y in got if y and not x), false_fail=sum(1 for x, y in got if x and not y),
                      disagreements=disagree[:40])
        print(f"{j:14} agreement {out[j]['agreement']:.1%}  kappa {out[j]['kappa']:.2f}  "
              f"false pass {out[j]['false_pass']}  false fail {out[j]['false_fail']}  ${cost:.2f}", flush=True)
    os.makedirs(os.path.join(ROOT, "results"), exist_ok=True)
    json.dump(out, open(os.path.join(ROOT, "results", "judge_validation.json"), "w"), indent=1)


if __name__ == "__main__":
    main()
