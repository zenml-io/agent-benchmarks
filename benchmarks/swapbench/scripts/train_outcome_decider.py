"""Train the outcome-based handoff decider for the live replay (no rule text anywhere).

  python scripts/train_outcome_decider.py <raw-root> <out.pkl> [--exclude qwen3.8-27b,qwen27b]   (tau2 venv + scikit-learn)

Training data: proposed `escalate_to_human` actions in the visible and pool splits only (never the hidden set the
replay is graded on), from every bank run except the excluded models. Label: did the conversation end unresolved
(what a real outcome log gives). Threshold: flags at most 6% of handoffs in conversations that ended resolved.
"""
import argparse
import glob
import json
import os
import pickle
import sys

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scripts.jev_calibrate import items  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("root")
ap.add_argument("out")
ap.add_argument("--exclude", default="qwen3.8-27b,qwen27b")
a = ap.parse_args()
excl = [x for x in a.exclude.lower().split(",") if x]
X, y = [], []
for split in ("pool", "train"):
    for p in glob.glob(os.path.join(a.root, f"f*/**/{split}/results.json"), recursive=True) + \
             glob.glob(os.path.join(a.root, f"prov_hidden/[!_]*/{split}/results.json")):
        if "/guard/" in p or "/rft/" in p or any(e in p.lower() for e in excl):
            continue
        rewards = {(s["task_id"], s["trial"]): (s.get("reward_info") or {}).get("reward", 0)
                   for s in json.load(open(p))["simulations"] if s.get("reward_info")}
        for it in items(p, p):
            if it["tool"] == "escalate_to_human":
                X.append(it["state"].split("\n\nPROPOSED ACTION:")[0][-3000:])
                y.append(rewards.get((it["scenario"], it["trial"]), 0) < 1)
X, y = np.array(X), np.array(y)
vec = TfidfVectorizer(ngram_range=(1, 2), min_df=3, max_features=50000, sublinear_tf=True)
clf = LogisticRegression(max_iter=2000, class_weight="balanced", C=2.0).fit(vec.fit_transform(X), y)
# threshold from out-of-fold scores, so it reflects unseen conversations rather than the training fit
from sklearn.model_selection import StratifiedKFold  # noqa: E402
s = np.zeros(len(y))
for tr, te in StratifiedKFold(5, shuffle=True, random_state=0).split(X, y):
    v = TfidfVectorizer(ngram_range=(1, 2), min_df=3, max_features=50000, sublinear_tf=True)
    c = LogisticRegression(max_iter=2000, class_weight="balanced", C=2.0).fit(v.fit_transform(X[tr]), y[tr])
    s[te] = c.predict_proba(v.transform(X[te]))[:, 1]
thr = float(np.quantile(s[~y], 0.94))
pickle.dump(dict(vec=vec, clf=clf, threshold=thr), open(a.out, "wb"))
print(f"trained on {len(y)} handoffs ({y.sum()} in unresolved conversations), excluded {excl}; threshold {thr:.3f}")
