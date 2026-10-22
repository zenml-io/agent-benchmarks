"""Paired comparison of a candidate against a reference on the same scenarios.

Copied unchanged (per_scenario and paired_delta only) from SwapBench's swapbench/stats.py, which
the original export scripts imported.

Scenarios are the unit of resampling (cluster bootstrap): each scenario's trials are averaged
first, then scenarios are resampled with replacement. This keeps per-scenario difficulty paired
and treats repeated trials as what they are, extra measurements of the same item.
"""
import random
from collections import defaultdict


def per_scenario(episodes, key):
    acc = defaultdict(list)
    for e in episodes:  # episodes that crashed (API errors) count with reward 0: a swap that breaks is a regression
        acc[e["scenario"]].append(float(e[key]))
    return {s: sum(v) / len(v) for s, v in acc.items()}


def paired_delta(cand, inc, key="reward", n_boot=10000, seed=0):
    """Mean over shared scenarios of (candidate - incumbent), with a 95% cluster-bootstrap CI."""
    c, i = per_scenario(cand, key), per_scenario(inc, key)
    shared = sorted(set(c) & set(i))
    d = [c[s] - i[s] for s in shared]
    if not d:
        return dict(delta=None, lo=None, hi=None, n=0)
    rng = random.Random(seed)
    boots = sorted(sum(rng.choice(d) for _ in d) / len(d) for _ in range(n_boot))
    return dict(delta=sum(d) / len(d), lo=boots[int(0.025 * n_boot)], hi=boots[int(0.975 * n_boot) - 1],
                n=len(d), flips_down=sum(x <= -0.5 for x in d), flips_up=sum(x >= 0.5 for x in d))
