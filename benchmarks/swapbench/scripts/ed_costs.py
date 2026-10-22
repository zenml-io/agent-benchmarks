"""Expert-deciders benchmark: API spend tally for costs.md.

  python scripts/ed_costs.py <ed-dir> <edon-dir> > experiments/expert_deciders_costs.md   (tau2 venv)

Offline: expert labels (Claude Haiku 5.5, GPT-5 mini), judge D and the rubric (GPT-6.1 Sol), Jev (B, C, G at $0.042
per 1M input tokens), embeddings (text-embedding-3-small, estimated from step text). Live: every run in <edon-dir>
(agent calls incl. discarded ones, the Haiku customer simulator, and the check, estimated as in ed_online_eval.py),
including the runs stopped when the arms were trimmed (<edon-dir>/dropped) and the first DeepSeek runs lost to account
limits on another provider (<edon-dir>/provider-b_partial; their failed conversations still billed some calls). Token counts are from the logs; prices
from swapbench/pricing.py.
"""
import glob
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from swapbench import pricing  # noqa: E402
from ed_online_eval import cost as run_cost  # noqa: E402

JEV = 0.042 / 1e6
EMB = 0.02 / 1e6


def tok(path, key):
    return sum((json.loads(l).get(key) or 0) for l in open(path)) if os.path.exists(path) else 0


def main(ed, edon):
    rows = []
    L = [json.loads(l) for l in open(os.path.join(ed, "labels.jsonl"))]
    for e, model in (("claude", "claude-haiku-5-5"), ("gpt", "gpt-5-mini-2025-08-07")):
        x = [l for l in L if l["expert"] == e]
        i, o = sum(l.get("in_tok") or 0 for l in x), sum(l.get("out_tok") or 0 for l in x)
        rows.append((f"expert labels: {e} ({len(x)} answers)", f"{i:,} in / {o:,} out", pricing.cost(model, i, 0, o)))
    sc = os.path.join(ed, "scores")
    i, o = tok(f"{sc}/scores_D.jsonl", "in_tok"), tok(f"{sc}/scores_D.jsonl", "out_tok")
    rows.append(("judge D offline (GPT-6.1 Sol), 1,500 decisions", f"{i:,} in / {o:,} out", pricing.cost("gpt-6.1-sol", i, 0, o)))
    rows.append(("interview rubric (GPT-6.1 Sol, 3 calls, estimated)", "~60k in / ~15k out", pricing.cost("gpt-6.1-sol", 60000, 0, 15000)))
    for a in ("B", "C", "G"):
        i = tok(f"{sc}/scores_{a}.jsonl", "in_tok")
        rows.append((f"Jev offline arm {a}, 1,500 decisions", f"{i:,} in", i * JEV))
    steps = sum(len(json.loads(l)["state"]) for l in open(os.path.join(ed, "steps.jsonl")))
    rows.append(("embeddings (text-embedding-3-small, ~4 chars/token)", f"~{steps // 4:,} in", steps / 4 * EMB))
    off = sum(r[2] for r in rows)
    live = []
    for d in sorted(glob.glob(os.path.join(edon, "[ABR]_*")) + glob.glob(os.path.join(edon, "dropped", "[ABR]_*"))
                    + glob.glob(os.path.join(edon, "provider-b_partial", "[ABR]_*"))):
        if not os.path.isdir(d):
            continue
        res = glob.glob(os.path.join(d, "*", "test", "results.json"))
        sims = json.load(open(res[0]))["simulations"] if res else []
        if not sims:
            continue
        per, chk = run_cost(d, sims, None)
        user = sum(s.get("user_cost") or 0 for s in sims)
        tag = " (dropped)" if "dropped" in d else " (another provider, set aside)" if "provider-b_partial" in d else ""
        live.append((os.path.basename(d) + tag, len(sims), per * len(sims), user))
    print("# Expert-deciders benchmark: API spend\n")
    print("No GPU time is used.\n")
    print("## Offline (labels, arms, rubric)\n\n| item | tokens | USD |\n|---|---|---|")
    for n, t, c in rows:
        print(f"| {n} | {t} | {c:.2f} |")
    print(f"| **offline total** | | **{off:.2f}** |\n")
    print("## Live runs (bank hidden set x2)\n\n| run | conversations | agent + check USD | customer simulator USD |\n|---|---|---|---|")
    for n, k, c, u in live:
        print(f"| {n} | {k} | {c:.2f} | {u:.2f} |")
    lt = sum(c + u for _, _, c, u in live)
    print(f"| **live total** | | | **{lt:.2f}** |\n")
    print(f"**Benchmark total: ${off + lt:.2f}**.")


if __name__ == "__main__":
    main(*sys.argv[1:3])
