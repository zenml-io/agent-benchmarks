"""Summarize the tuned-harness benchmark on the held-out split.

  python harness/tuned_report.py

Every arm (effort level, tuned prompt, repeat) is compared with the same model's original run on the same held-out
cases: accuracy, paired difference with a bootstrap 95% interval, cost per correct decision. The repeat of Sonnet 5.5
(same prompt and settings, run again) shows how much accuracy moves when nothing changes. Then each model's best
arm, by accuracy with cost per correct decision breaking ties within a point, gives a tuned ranking next to the
original one. Writes results/tuned/summary.json and results/tuned/tables.md.
"""
import glob
import json
import os
import random
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HELD = set(json.load(open(os.path.join(ROOT, "env", "split.json")))["held"])
NAMES = {"opus-5.5": "Opus 5.5", "sonnet-5.5": "Sonnet 5.5", "haiku-5.5": "Haiku 5.5", "gpt-6.1-sol": "GPT-6.1 Sol",
         "gpt-6-luna": "GPT-6 Luna", "deepseek-v4-pro@provider-a": "DeepSeek V4 Pro",
         "glm-5.3-flash@provider-a": "GLM 5.3 Flash", "gpt-oss-120b@provider-a": "gpt-oss-120b",
         "deepseek-v4.1-flash@provider-a": "DeepSeek V4.1 Flash", "glm-5.3@provider-a": "GLM 5.3",
         "qwen3.8-27b@provider-a": "Qwen3.8 27B", "minimax-m3@provider-a": "MiniMax-M3"}


def load(path):
    rows = {}
    for line in open(path):
        r = json.loads(line)
        if r["status"] != "harness_error" and r["task"] in HELD:
            rows[r["task"]] = r
    return rows


def paired(a, b, rng, reps=4000):
    keys = sorted(set(a) & set(b))
    d = [int(a[k]["success"]) - int(b[k]["success"]) for k in keys]
    boots = sorted(sum(rng.choice(d) for _ in d) / len(d) for _ in range(reps))
    return dict(n=len(d), delta=sum(d) / len(d), lo=boots[int(reps * .025)], hi=boots[int(reps * .975)])


def stats(rows):
    n, k = len(rows), sum(r["success"] for r in rows.values())
    cost = sum(r["cost"] for r in rows.values())
    return dict(n=n, correct=k, accuracy=k / n if n else None, cost_per_task=cost / n if n else None,
                cost_per_correct=cost / k if k else None,
                failures={f: sum(f in r["failures"] for r in rows.values())
                          for f in {f for r in rows.values() for f in r["failures"]}})


def main():
    rng = random.Random(0)
    base = {os.path.basename(p)[:-6]: load(p) for p in glob.glob(os.path.join(ROOT, "results", "runs", "*.jsonl"))}
    arms = {}
    for p in glob.glob(os.path.join(ROOT, "results", "tuned", "runs", "*__*.jsonl")):
        model, arm = os.path.basename(p)[:-6].split("__")
        if re.fullmatch(r"tune\d+|smoke", arm):
            continue  # learning-split rounds and smoke tests are not held-out results
        arms.setdefault(model, {})[arm] = load(p)
    out = {}
    for model, by_arm in sorted(arms.items()):
        b = base[model]
        entry = {"original": stats(b)}
        for arm, rows in sorted(by_arm.items()):
            entry[arm] = stats(rows) | {"vs_original": paired(rows, b, rng)}
        hc = os.path.join(ROOT, "results", "tuned", "hillclimb", f"{model}.json")
        if os.path.exists(hc):
            entry["hillclimb"] = {k: v for k, v in json.load(open(hc)).items() if k != "rounds"} | {
                "rounds": [{k: v for k, v in r.items() if k != "why"} for r in json.load(open(hc))["rounds"]]}
        out[model] = entry
    best = {}
    for model, b in base.items():
        options = {"original": stats(b)} | {a: v for a, v in out.get(model, {}).items()
                                            if isinstance(v, dict) and "accuracy" in v and a != "repeat"}
        top = max(v["accuracy"] for v in options.values())
        near = {a: v for a, v in options.items() if v["accuracy"] >= top - 0.01}
        pick = min(near, key=lambda a: near[a]["cost_per_correct"] or 1e9)
        best[model] = dict(arm=pick, **options[pick], original_accuracy=options["original"]["accuracy"],
                           original_cost_per_correct=options["original"]["cost_per_correct"])
    noise = out.get("sonnet-5.5", {}).get("repeat", {}).get("vs_original")
    json.dump(dict(held_n=len(HELD), noise=noise, arms=out, best=best),
              open(os.path.join(ROOT, "results", "tuned", "summary.json"), "w"), indent=1)
    lines = [f"Held-out cases: {len(HELD)}. Noise (Sonnet 5.5 repeated, same settings): "
             + (f"{noise['delta'] * 100:+.1f} pts [{noise['lo'] * 100:+.1f}, {noise['hi'] * 100:+.1f}]" if noise else "n/a"),
             "", "| model | arm | correct | vs original (pts, 95% CI) | cost per correct |", "|---|---|---|---|---|"]
    for model, entry in out.items():
        o = entry["original"]
        lines.append(f"| {NAMES.get(model, model)} | original | {o['accuracy']:.1%} | | {o['cost_per_correct'] * 100:.2f}¢ |")
        for arm, v in entry.items():
            if arm in ("original", "hillclimb"):
                continue
            d = v["vs_original"]
            lines.append(f"| | {arm} | {v['accuracy']:.1%} | {d['delta'] * 100:+.1f} [{d['lo'] * 100:+.1f}, "
                         f"{d['hi'] * 100:+.1f}] | {(v['cost_per_correct'] or 0) * 100:.2f}¢ |")
    lines += ["", "Best setup per model (highest accuracy; within 1 point, lowest cost per correct decision):", "",
              "| model | best arm | correct | original | cost per correct | original |", "|---|---|---|---|---|---|"]
    for model in sorted(best, key=lambda m: -best[m]["accuracy"]):
        v = best[model]
        lines.append(f"| {NAMES.get(model, model)} | {v['arm']} | {v['accuracy']:.1%} | {v['original_accuracy']:.1%} | "
                     f"{v['cost_per_correct'] * 100:.2f}¢ | {v['original_cost_per_correct'] * 100:.2f}¢ |")
    lines += ["", "One shared prompt (Sonnet 5.5's tuned prompt) against each model's own tuned prompt:", "",
              "| model | original | shared prompt | own tuned prompt | cost per correct: original, shared, own |",
              "|---|---|---|---|---|"]
    for model in sorted(out, key=lambda m: -(out[m].get("shared", out[m].get("tuned", out[m]["original"]))["accuracy"])):
        e = out[model]
        shared = e.get("shared") or (e.get("tuned") if model == "sonnet-5.5" else None)
        own = e.get("tuned")

        def cell(v):
            if not v:
                return "–"
            d = v.get("vs_original")
            return f"{v['accuracy']:.1%}" + (f" ({d['delta'] * 100:+.1f} [{d['lo'] * 100:+.1f}, {d['hi'] * 100:+.1f}])" if d else "")

        costs = ", ".join(f"{v['cost_per_correct'] * 100:.2f}¢" if v and v["cost_per_correct"] else "–"
                          for v in (e["original"], shared, own))
        lines.append(f"| {NAMES.get(model, model)} | {e['original']['accuracy']:.1%} | {cell(shared)} | {cell(own)} | {costs} |")
    open(os.path.join(ROOT, "results", "tuned", "tables.md"), "w").write("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
