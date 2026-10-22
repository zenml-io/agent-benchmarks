"""Re-grade the models that also judge, with judges other than themselves.

  python harness/regrade_self.py

The benchmark's judges (GPT-6 Luna and Claude Haiku 5.5, GPT-6.1 Sol breaking ties) are also candidates, so each graded
its own answers. A model may favor answers like its own. For each of those three models, every final answer is graded
again by the two judges among Luna, Haiku and Sol that are not the model, with Claude Opus 5.5 breaking ties.
Unfinished runs stay wrong. Writes results/regrade_self.json; the judge spend is printed and goes in costs.md.
"""
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from judge import grade  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JUDGES = ("gpt-6-luna", "haiku-5.5", "gpt-6.1-sol")
TIEBREAK = "opus-5.5"


def regrade(model, row):
    if not row.get("final_answer"):
        return row["task"], False, False, 0.0
    judges = [j for j in JUDGES if j != model]
    votes = [grade(j, row["task_type"], TASKS[row["task"]]["reference"], row["final_answer"]) for j in judges]
    cost = sum(v[2] for v in votes)
    if votes[0][0] != votes[1][0] or votes[0][0] is None:
        tie = grade(TIEBREAK, row["task_type"], TASKS[row["task"]]["reference"], row["final_answer"])
        votes.append(tie)
        cost += tie[2]
    return row["task"], bool(row["success"]), bool(votes[-1][0]), cost


TASKS = {t["id"]: t for t in json.load(open(os.path.join(ROOT, "env", "tasks.json")))}


def main():
    out, spend = {}, 0.0
    for model in JUDGES:
        rows = {}
        for line in open(os.path.join(ROOT, "results", "runs", f"{model}.jsonl")):
            r = json.loads(line)
            if r["status"] != "harness_error":
                rows[r["task"]] = r
        with ThreadPoolExecutor(16) as ex:
            res = list(ex.map(lambda r: regrade(model, r), rows.values()))
        spend += sum(c for *_, c in res)
        before = sum(b for _, b, _, _ in res)
        after = sum(a for _, _, a, _ in res)
        flips = [(t, b, a) for t, b, a, _ in res if b != a]
        out[model] = dict(n=len(res), before=before, after=after, flips=flips)
        print(f"{model:12} n={len(res)} correct before {before} ({before / len(res):.1%}) "
              f"after {after} ({after / len(res):.1%}); changed {len(flips)} "
              f"(+{sum(a for _, _, a in flips)} / -{sum(b for _, b, _ in flips)})", flush=True)
    print(f"judge spend ${spend:.2f}")
    json.dump(dict(models=out, spend=spend),
              open(os.path.join(ROOT, "results", "regrade_self.json"), "w"), indent=1)


if __name__ == "__main__":
    main()
