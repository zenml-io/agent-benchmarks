"""Expert-deciders benchmark: save what the live checks need (small models, judge examples).

  python scripts/ed_online_prep.py <steps.jsonl> <labels.jsonl> <scores-dir> [--n 200]     (tau2 venv + scikit-learn)

Writes <scores-dir>/online_E{n}.pkl (per decision point: an embeddings + logistic-regression model fit on the same
interview-style selection of n expert labels as arm E-n) and <scores-dir>/judge_examples.json (arm D's 10 examples).
"""
import argparse
import json
import os
import pickle
import random
import sys
from collections import defaultdict

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scripts.ed_arms import POINTS, embed, fit, small_arm, state_text  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("steps")
ap.add_argument("labels")
ap.add_argument("out")
ap.add_argument("--n", type=int, default=200)
a = ap.parse_args()
steps = [json.loads(l) for l in open(a.steps)]
by_id = {s["id"]: s for s in steps}
labels = [json.loads(l) for l in open(a.labels) if json.loads(l).get("go_ahead") is not None]
train_lab = [l for l in labels if l["expert"] == "claude" and not by_id[l["id"]]["heldout"] and by_id[l["id"]]["agent"] == "A"]
random.Random(0).shuffle(train_lab)
lab_by_point = defaultdict(list)
for l in train_lab:
    lab_by_point[by_id[l["id"]]["point"]].append(l)
cache_p = os.path.join(a.out, "emb_cache.json")
cache = json.load(open(cache_p))
models, examples = {}, {}
rng = random.Random(1)
for p in POINTS:
    L = lab_by_point[p]
    tr = [by_id[l["id"]] for l in L]
    y = np.array([not l["go_ahead"] for l in L])
    X = embed([state_text(s) for s in tr], cache)
    _, chosen = small_arm(y, X, X[:2], sizes=(25, 50, 100, 200, 400))
    sel = chosen[: a.n]
    models[p] = fit(X[sel], y[sel])
    pos = [l for l in L[:400] if not l["go_ahead"]]
    neg = [l for l in L[:400] if l["go_ahead"]]
    pick = rng.sample(pos, min(5, len(pos))) + rng.sample(neg, min(5, len(neg)))
    examples[p] = [[by_id[l["id"]], not l["go_ahead"]] for l in pick]
json.dump(cache, open(cache_p, "w"))
pickle.dump(models, open(os.path.join(a.out, f"online_E{a.n}.pkl"), "wb"))
json.dump(examples, open(os.path.join(a.out, "judge_examples.json"), "w"))
print("saved", {p: int(m.coef_.shape[1]) for p, m in models.items()})

# Hybrid arm: the word-count (TF-IDF) model on 400 interview labels for handoffs, as arm T400 offline.
from sklearn.feature_extraction.text import TfidfVectorizer  # noqa: E402
L = lab_by_point["handoff"]
tr = [by_id[l["id"]] for l in L]
y = np.array([not l["go_ahead"] for l in L])
vec = TfidfVectorizer(ngram_range=(1, 2), min_df=2, max_features=40000, sublinear_tf=True)
T = vec.fit_transform([state_text(s) for s in tr])
_, chosen = small_arm(y, T, T[:2], sizes=(25, 50, 100, 200, 400))
sel = chosen[:400]
pickle.dump(dict(vec=vec, clf=fit(T[sel], y[sel])), open(os.path.join(a.out, "online_T400_handoff.pkl"), "wb"))
print("saved handoff word-count model on", len(sel), "labels")
