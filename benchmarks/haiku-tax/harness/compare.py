"""Paired comparisons on the same tasks with bootstrap 95% intervals.

  python harness/compare.py <results-dir> <use_case|all> <model_a> <model_b> [--arm-a none] [--arm-b none]

Success difference (a - b) in points over the tasks both models finished (tasks that ended in an API error for either
are left out). With "all", tasks are pooled over use cases and resampled within each use case (stratified bootstrap).
Also prints the cost-per-success ratio with a bootstrap interval. Says "not enough evidence" when the interval for the
difference includes zero.
"""
import argparse
import glob
import json
import os
import random

INFRA = ("api_error", "account_blocked", "timeout")


def load(root, uc, model, arm):
    out = {}
    for p in glob.glob(os.path.join(root, uc, f"{model}__{arm}.jsonl")):
        u = os.path.basename(os.path.dirname(p))
        for l in open(p):
            r = json.loads(l)
            out[(u, r["task"])] = r
    return {k: r for k, r in out.items() if r["status"] not in INFRA}


def paired(a, b, n_boot=4000, seed=0):
    keys = sorted(set(a) & set(b))
    by_uc = {}
    for k in keys:
        by_uc.setdefault(k[0], []).append(k)
    rng = random.Random(seed)

    def stat(ks):
        n = len(ks)
        sa = sum(a[k]["success"] for k in ks)
        sb = sum(b[k]["success"] for k in ks)
        ca = sum(a[k]["cost"] for k in ks)
        cb = sum(b[k]["cost"] for k in ks)
        return (sa - sb) / n * 100, (ca / sa if sa else float("inf")) / (cb / sb if sb else float("inf"))

    d0, r0 = stat(keys)
    ds, rs = [], []
    for _ in range(n_boot):
        ks = [k for g in by_uc.values() for k in (rng.choice(g) for _ in g)]
        d, r = stat(ks)
        ds.append(d)
        rs.append(r)
    ds.sort()
    rs.sort()
    lo, hi = ds[int(0.025 * n_boot)], ds[int(0.975 * n_boot) - 1]
    return dict(n=len(keys), delta=d0, lo=lo, hi=hi, cost_ratio=r0,
                ratio_lo=rs[int(0.025 * n_boot)], ratio_hi=rs[int(0.975 * n_boot) - 1],
                verdict="not enough evidence" if lo <= 0 <= hi else ("a better" if lo > 0 else "b better"),
                success_a=sum(a[k]["success"] for k in keys) / len(keys) * 100,
                success_b=sum(b[k]["success"] for k in keys) / len(keys) * 100)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("root")
    ap.add_argument("use_case")
    ap.add_argument("a")
    ap.add_argument("b")
    ap.add_argument("--arm-a", default="none")
    ap.add_argument("--arm-b", default="none")
    x = ap.parse_args()
    uc = "*" if x.use_case == "all" else x.use_case
    r = paired(load(x.root, uc, x.a, x.arm_a), load(x.root, uc, x.b, x.arm_b))
    print(f"{x.use_case}: {x.a}/{x.arm_a} {r['success_a']:.1f}% vs {x.b}/{x.arm_b} {r['success_b']:.1f}% on {r['n']} "
          f"shared tasks: {r['delta']:+.1f} pts [{r['lo']:+.1f}, {r['hi']:+.1f}] ({r['verdict']}); cost per success "
          f"ratio a/b {r['cost_ratio']:.2f} [{r['ratio_lo']:.2f}, {r['ratio_hi']:.2f}]")


if __name__ == "__main__":
    main()
