"""Can a small model learn the unwritten handoff rule from outcomes alone, with no rule written down?

  python scripts/outcome_decider.py <raw-root> [--tool escalate_to_human]      (tau2 venv + scikit-learn)

Data: every proposed `escalate_to_human` (or another write tool) in the bank agents' hidden-set transcripts (GPT-5,
GPT-6 Luna, GPT-5.4 nano, Qwen BF16/FP8, the hosted providers' runs), with the conversation up to that point.
Two kinds of label, both learned without the policy text:
- action label: was this action one of the scenario's gold actions? (what a perfect per-decision outcome log gives)
- conversation label: did the conversation end resolved? (what a real outcome log gives: noisy credit assignment)
Model: TF-IDF over the last 3,000 characters of the conversation + logistic regression. Evaluation: scenarios are
split into folds so test scenarios are never seen in training; plus a "new model" test trained without any Qwen
conversations and tested on Qwen's. Reported: share of wrong actions flagged at a threshold that wrongly flags at most
6% of right actions (Jev with the written rule: 60% at 6%; Jev without it: 0%).
"""
import argparse
import glob
import os
import sys

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import GroupKFold

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scripts.jev_calibrate import items  # noqa: E402
import json  # noqa: E402


def load(root, tool):
    paths = [p for p in glob.glob(os.path.join(root, "f*/**/test/results.json"), recursive=True)
             if "/guard/" not in p and "/rft/" not in p] + glob.glob(os.path.join(root, "prov_hidden/[!_]*/test/results.json"))
    rows = []
    for p in paths:
        run = os.path.relpath(os.path.dirname(os.path.dirname(p)), root)
        rewards = {(s["task_id"], s["trial"]): (s.get("reward_info") or {}).get("reward", 0)
                   for s in json.load(open(p))["simulations"] if s.get("reward_info")}
        for it in items(p, run):
            if it["tool"] == tool:
                it["resolved"] = rewards.get((it["scenario"], it["trial"]), 0) >= 1
                it["qwen"] = "qwen" in run.lower()
                rows.append(it)
    return rows


def recall_at(scores_wrong, scores_right, max_fp=0.06):
    thr = np.quantile(scores_right, 1 - max_fp)
    return float(np.mean(scores_wrong > thr)), float(np.mean(scores_right > thr))


def fit_predict(Xtr_text, ytr, Xte_text):
    vec = TfidfVectorizer(ngram_range=(1, 2), min_df=3, max_features=50000, sublinear_tf=True)
    clf = LogisticRegression(max_iter=2000, class_weight="balanced", C=2.0)
    clf.fit(vec.fit_transform(Xtr_text), ytr)
    return clf.predict_proba(vec.transform(Xte_text))[:, 1]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("root")
    ap.add_argument("--tool", default="escalate_to_human")
    a = ap.parse_args()
    rows = load(a.root, a.tool)
    text = np.array([r["state"][-3000:] for r in rows])
    wrong = np.array([not r["right"] for r in rows])
    bad_end = np.array([not r["resolved"] for r in rows])
    groups = np.array([r["scenario"] for r in rows])
    qwen = np.array([r["qwen"] for r in rows])
    print(f"# Learning the {a.tool} rule from outcomes\n")
    print(f"{len(rows)} proposed actions; {wrong.sum()} wrong by the gold; {bad_end.sum()} in conversations that did not "
          f"end resolved; {qwen.sum()} from Qwen runs.\n")
    print("| label the model learns from | test | AUC (wrong vs right) | wrong actions flagged | right actions flagged |")
    print("|---|---|---|---|---|")
    for lname, y in [("action outcome (was it a gold action?)", wrong), ("conversation outcome (did it end resolved?)", bad_end)]:
        scores = np.zeros(len(rows))
        for tr, te in GroupKFold(n_splits=5).split(text, y, groups):
            scores[te] = fit_predict(text[tr], y[tr], text[te])
        auc = roc_auc_score(wrong, scores)
        r, f = recall_at(scores[wrong], scores[~wrong])
        print(f"| {lname} | unseen scenarios (5-fold) | {auc:.2f} | {r:.0%} | {f:.0%} |")
        tr, te = ~qwen, qwen
        s = fit_predict(text[tr], y[tr], text[te])
        auc = roc_auc_score(wrong[te], s)
        r, f = recall_at(s[wrong[te]], s[~wrong[te]])
        print(f"| {lname} | new model: trained without Qwen, tested on Qwen | {auc:.2f} | {r:.0%} | {f:.0%} |")
    print("\nReference on the same decisions (scripts/jev_calibrate.py): Jev with the written handoff rule flags 60% of "
          "wrong handoffs at 6% of right ones; without the rule, 0%.")


if __name__ == "__main__":
    main()
