"""Expert-deciders benchmark, step 4: offline evaluation of every arm on held-out steps.

  python scripts/ed_eval.py <steps.jsonl> <labels.jsonl> <scores-dir> > experiments/expert_deciders_offline.md

Targets: (1) the hidden-rule truth (programmatic) and (2) the two experts' consensus (steps where they agree).
Metrics per arm, decision point and agent: precision / recall / F1 on "should not happen" at p > 0.5; expected
calibration error (ECE, 10 bins) raw and after temperature scaling (fit by 5-fold cross-fitting on the held-out set);
selective accuracy with the 20% least-sure cases escalated; share escalated by conformal allow/block thresholds set for
<= 5% error on each side (cross-fitted). Also: expert agreement (Cohen's kappa), and the learning curve for E/T.
"""
import glob
import json
import os
import sys
from collections import defaultdict

import numpy as np

POINTS = ("handoff", "refund", "card")


def kappa(a, b):
    a, b = np.array(a), np.array(b)
    po = np.mean(a == b)
    pe = np.mean(a) * np.mean(b) + (1 - np.mean(a)) * (1 - np.mean(b))
    return (po - pe) / (1 - pe) if pe < 1 else 1.0


def ece(p, y, bins=10):
    p, y = np.asarray(p), np.asarray(y)
    e = 0.0
    for i in range(bins):
        m = (p >= i / bins) & (p < (i + 1) / bins if i < bins - 1 else p <= 1)
        if m.any():
            e += m.mean() * abs(p[m].mean() - y[m].mean())
    return e


def temp_scale(p, y, folds=5):
    """Cross-fitted Platt-style scaling of logit(p): returns calibrated probabilities."""
    from sklearn.linear_model import LogisticRegression
    p = np.clip(np.asarray(p, float), 1e-4, 1 - 1e-4)
    z = np.log(p / (1 - p)).reshape(-1, 1)
    out = np.zeros(len(p))
    idx = np.arange(len(p))
    rng = np.random.RandomState(0)
    rng.shuffle(idx)
    for k in range(folds):
        te = idx[k::folds]
        tr = np.setdiff1d(idx, te)
        if len(set(y[tr])) < 2:
            out[te] = p[te]
            continue
        m = LogisticRegression().fit(z[tr], y[tr])
        out[te] = m.predict_proba(z[te])[:, 1]
    return out


def conformal_escalate(pc, y, err=0.05, folds=5):
    """Share of cases escalated when allow/block thresholds keep <= err wrong decisions on each side (cross-fitted)."""
    idx = np.arange(len(pc))
    esc, wrong = 0, 0
    for k in range(folds):
        te, tr = idx[k::folds], np.setdiff1d(idx, idx[k::folds])
        lo = max([t for t in np.linspace(0, 1, 101) if np.mean(y[tr][pc[tr] <= t]) <= err] or [0.0]) if len(tr) else 0
        hi = min([t for t in np.linspace(0, 1, 101) if np.mean(1 - y[tr][pc[tr] >= t]) <= err] or [1.0]) if len(tr) else 1
        allow, block = pc[te] <= lo, pc[te] >= max(hi, lo)
        esc += np.sum(~allow & ~block)
        wrong += np.sum(y[te][allow]) + np.sum(1 - y[te][block])
    return esc / len(pc), wrong / max(len(pc) - esc, 1)


def metrics(p, y):
    p, y = np.asarray(p, float), np.asarray(y, int)
    pred = p > 0.5
    tp, fp, fn = np.sum(pred & (y == 1)), np.sum(pred & (y == 0)), np.sum(~pred & (y == 1))
    prec = tp / max(tp + fp, 1)
    rec = tp / max(tp + fn, 1)
    f1 = 2 * prec * rec / max(prec + rec, 1e-9)
    pc = temp_scale(p, y)
    keep = np.argsort(np.abs(pc - 0.5))[int(0.2 * len(pc)):]
    sel = np.mean((pc[keep] > 0.5) == y[keep])
    esc, err = conformal_escalate(pc, y)
    return dict(n=len(y), pos=int(y.sum()), prec=prec, rec=rec, f1=f1, ece=ece(p, y), ece_ts=ece(pc, y), sel=sel,
                esc=esc, err=err)


def main(steps_p, labels_p, scores_dir):
    steps = {json.loads(l)["id"]: json.loads(l) for l in open(steps_p)}
    labels = defaultdict(dict)
    for l in map(json.loads, open(labels_p)):
        if l.get("go_ahead") is not None:
            labels[l["id"]][l["expert"]] = not l["go_ahead"]
    test = {i: s for i, s in steps.items() if s["heldout"]}
    both = {i: v for i, v in labels.items() if i in test and len(v) == 2}
    print("# Expert-deciders benchmark: offline results\n")
    print("## Gate: do the two simulated experts agree?\n")
    print("| decision | steps both experts labelled | agreement | Cohen's kappa | expert vs hidden-rule truth (claude / gpt) |")
    print("|---|---|---|---|---|")
    for pt in POINTS:
        ids = [i for i in both if test[i]["point"] == pt]
        a = [both[i]["claude"] for i in ids]
        b = [both[i]["gpt"] for i in ids]
        t = [test[i]["bad"] for i in ids]
        print(f"| {pt} | {len(ids)} | {np.mean(np.array(a) == np.array(b)):.0%} | {kappa(a, b):.2f} | "
              f"{np.mean(np.array(a) == np.array(t)):.0%} / {np.mean(np.array(b) == np.array(t)):.0%} |")
    arms = sorted(os.path.basename(f)[7:-6] for f in glob.glob(os.path.join(scores_dir, "scores_*.jsonl")))
    S = {a: {r["id"]: r for r in map(json.loads, open(os.path.join(scores_dir, f"scores_{a}.jsonl"))) if r.get("p") is not None}
         for a in arms}
    for target in ("truth", "consensus"):
        print(f"\n## Against the {'hidden-rule truth' if target == 'truth' else 'experts consensus (steps they agree on)'}\n")
        print("| arm | agent | decision | n (bad) | precision | recall | F1 | ECE raw → scaled | selective acc. @20% esc. | conformal escalate share (error) |")
        print("|---|---|---|---|---|---|---|---|---|---|")
        for a in arms:
            for agent in ("A", "B"):
                for pt in POINTS:
                    ids = [i for i, s in test.items() if s["agent"] == agent and s["point"] == pt and i in S[a]]
                    if target == "consensus":
                        ids = [i for i in ids if i in both and both[i]["claude"] == both[i]["gpt"]]
                        y = [both[i]["claude"] for i in ids]
                    else:
                        y = [test[i]["bad"] for i in ids]
                    if len(ids) < 20 or len(set(y)) < 2:
                        continue
                    m = metrics([S[a][i]["p"] for i in ids], y)
                    print(f"| {a} | {agent} | {pt} | {m['n']} ({m['pos']}) | {m['prec']:.2f} | {m['rec']:.2f} | "
                          f"**{m['f1']:.2f}** | {m['ece']:.2f} → {m['ece_ts']:.2f} | {m['sel']:.2f} | {m['esc']:.0%} ({m['err']:.1%}) |")
    print("\n## Cost and latency per decision\n")
    print("| arm | mean input tokens | median latency (s) |\n|---|---|---|")
    for a in arms:
        rows = list(S[a].values())
        it = [r["in_tok"] for r in rows if r.get("in_tok")]
        lt = sorted(r["latency"] for r in rows if r.get("latency"))
        if it or lt:
            print(f"| {a} | {np.mean(it):.0f} | {lt[len(lt) // 2] if lt else float('nan'):.2f} |")


if __name__ == "__main__":
    main(*sys.argv[1:4])
