"""Open-model (self-hosted) candidates vs the incumbent on a task's hidden set.
  python scripts/compare_open.py <incumbent results.json> <openmodel dir> [--split test]"""
import collections
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from swapbench import stats, tau2_adapter  # noqa: E402

inc_path, root = sys.argv[1], sys.argv[2]
split = sys.argv[sys.argv.index("--split") + 1] if "--split" in sys.argv else "test"
inc = tau2_adapter.load(inc_path)
runs = {}
for l in open(os.path.join(root, "runs.jsonl")):
    r = json.loads(l)
    if r.get("split") == split and "run_s" in r:
        runs[r["config"]] = r
print(f"| config | episodes | pass^1 | Δ vs incumbent [95% CI] | harmful writes/conv | GPU $/conv (c={next(iter(runs.values()))['concurrency']}) | cost cut | label |")
print("|---|---|---|---|---|---|---|---|")
for c, r in sorted(runs.items()):
    eps = tau2_adapter.load(os.path.join(root, c, split, "results.json"))
    q, h = stats.paired_delta(eps, inc, "reward"), stats.paired_delta(eps, inc, "harmful_writes")
    cpe = r["run_s"] / 3600 * r["gpu_price_per_h"] / len(eps)
    print(f"| {c} | {len(eps)} | {stats.mean(eps, 'reward'):.3f} | {q['delta']*100:+.1f} [{q['lo']*100:+.1f}, {q['hi']*100:+.1f}] | "
          f"{stats.mean(eps, 'harmful_writes'):.3f} | ${cpe:.4f} | {(1 - cpe / stats.mean(inc, 'cost_usd'))*100:.0f}% | "
          f"{stats.truth_label(q, h, 0.05)} |")
print(f"\nIncumbent: pass^1 {stats.mean(inc, 'reward'):.3f}, ${stats.mean(inc, 'cost_usd'):.4f}/conv, harmful writes {stats.mean(inc, 'harmful_writes'):.3f}/conv")
