"""Compare candidates with the incumbent on the visible and hidden sets of a task.

  python -m swapbench.compare <ground_truth_dir> --incumbent gpt-5-2025-08-07 [--margin 0.05] [--md out.md]

<ground_truth_dir>/<model_tag>/{train,test}/results.json as written by scripts/gt_one.sh
(train = visible set V, test = hidden set H).
"""
import argparse
import glob
import json
import os

from . import stats, tau2_adapter


def load_dir(root):
    out = {}
    for res in glob.glob(os.path.join(root, "*", "*", "results.json")):
        tag, split = res.split(os.sep)[-3:-1]
        eps = tau2_adapter.load(res)
        out.setdefault(eps[0]["model"] if eps else tag, {})[split] = eps
    return out


def row(name, eps, inc, margin):
    r = dict(model=name, n=len(eps), errors=sum(e["infra_error"] for e in eps),
             reward=stats.mean(eps, "reward"), cost=stats.mean(eps, "cost_usd"),
             harm=stats.mean(eps, "harmful_writes"))
    q = stats.paired_delta(eps, inc, "reward") if inc and eps is not inc else {"n": 0}
    if q["n"]:
        h = stats.paired_delta(eps, inc, "harmful_writes")
        r.update(delta=q["delta"], lo=q["lo"], hi=q["hi"], flips_down=q["flips_down"], flips_up=q["flips_up"],
                 harm_delta=h["delta"], label=stats.truth_label(q, h, margin),
                 cost_cut=1 - r["cost"] / stats.mean(inc, "cost_usd"))
    return r


def fmt(rows, split):
    lines = [f"\n### {split}\n",
             "| model | episodes | API errors | pass^1 | $/episode | cost cut | Δ pass^1 [95% CI] | flips ↓/↑ | harmful writes/ep (Δ) | label |",
             "|---|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        d = (f"{r['delta']*100:+.1f} [{r['lo']*100:+.1f}, {r['hi']*100:+.1f}]" if "delta" in r else "incumbent")
        lines.append(f"| {r['model']} | {r['n']} | {r['errors']} | {r['reward']:.3f} | ${r['cost']:.4f} | "
                     f"{r.get('cost_cut', 0)*100:.0f}% | {d} | {r.get('flips_down', '')}/{r.get('flips_up', '')} | "
                     f"{r['harm']:.3f} ({r.get('harm_delta', 0):+.3f}) | {r.get('label', '')} |")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("root")
    ap.add_argument("--incumbent", required=True)
    ap.add_argument("--margin", type=float, default=0.05)
    ap.add_argument("--md")
    a = ap.parse_args()
    data = load_dir(a.root)
    out = [f"Margin δ = {a.margin*100:.0f} pts. Labels on the visible set are what a careful team could conclude from V alone;"
           " labels on the hidden set are the ground truth."]
    summary = {}
    for split, title in (("train", "Visible set V (tau2 train)"), ("test", "Hidden set H (tau2 test)")):
        inc = data.get(a.incumbent, {}).get(split)
        rows = [row(m, d[split], inc, a.margin) for m, d in sorted(data.items(), key=lambda kv: kv[0] != a.incumbent)
                if split in d]
        out.append(fmt(rows, title))
        summary[split] = rows
    text = "\n".join(out)
    print(text)
    if a.md:
        open(a.md, "w").write(text + "\n")
        json.dump(summary, open(os.path.splitext(a.md)[0] + ".json", "w"), indent=1)


if __name__ == "__main__":
    main()
