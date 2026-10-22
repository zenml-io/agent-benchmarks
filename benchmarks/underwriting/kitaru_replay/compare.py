"""Read the Kitaru full-replay experiments back and compare them with the benchmark's own full runs.

  KITARU_API_URL=... <kitaru venv>/bin/python kitaru_replay/compare.py

For each experiment (one model override on the 48 recorded Sonnet 5.5 cases): the correct-decision evaluation of every
baseline and replay session, the agent cost Kitaru recorded, and the paired difference against the baseline with a
bootstrap 95% interval. The benchmark's numbers for the same model on the same 48 tasks sit beside them (an
independent run, so they agree only up to run-to-run noise). Writes kitaru_replay/results.json.
"""
import asyncio
import json
import os
import random

from kitaru.api_models.v1.evaluation import EvaluationListParams
from kitaru.api_models.v1.replay import ReplayListParams
from kitaru.client.api_client import KitaruAPIClient

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)


def paired(a, b, rng, reps=4000):
    keys = sorted(set(a) & set(b))
    d = [int(a[k]) - int(b[k]) for k in keys]
    boots = sorted(sum(rng.choice(d) for _ in d) / len(d) for _ in range(reps))
    return dict(n=len(d), delta=sum(d) / len(d), lo=boots[int(reps * .025)], hi=boots[int(reps * .975)])


def bench(model, tasks):
    rows = {}
    for line in open(os.path.join(ROOT, "results", "runs", f"{model}.jsonl")):
        r = json.loads(line)
        if r["status"] != "harness_error" and r["task"] in tasks:
            rows[r["task"]] = r
    return rows


async def main():
    tasks = set(json.load(open(os.path.join(HERE, "cohort_tasks.json"))))
    rng = random.Random(0)
    async with KitaruAPIClient() as client:
        replays = [r async for r in client.replays.iter(ReplayListParams())]
        evals = {}
        async for ev in client.evaluations.iter(EvaluationListParams()):
            if ev.name == "correct_decision":
                evals[ev.session_id] = bool(ev.passed)
        runs = {}
        sessions = {}
        for r in replays:
            if r.experiment_run_id is None or r.result_session_id is None:
                continue
            runs.setdefault(r.experiment_run_id, []).append(r)
            for sid in (r.baseline_session_id, r.result_session_id):
                if sid not in sessions:
                    sessions[sid] = await client.sessions.get(sid)
    out = {}
    sonnet = bench("sonnet-5.5", tasks)
    for run_id, rs in runs.items():
        model = rs[0].override.model["sonnet-5.5"]
        base, new, cost_b, cost_n = {}, {}, 0.0, 0.0
        for r in rs:
            b, n = sessions[r.baseline_session_id], sessions[r.result_session_id]
            t = b.inputs["task_id"]
            if r.baseline_session_id in evals and r.result_session_id in evals:
                base[t], new[t] = evals[r.baseline_session_id], evals[r.result_session_id]
                cost_b += float(b.cost or 0)
                cost_n += float(n.cost or 0)
        bm = bench(model, tasks)
        out[model] = dict(
            experiment_run=str(run_id), n=len(new), baseline_correct=sum(base.values()), replay_correct=sum(new.values()),
            vs_baseline=paired(new, base, rng), baseline_cost=cost_b, replay_cost=cost_n,
            replay_cost_per_correct=cost_n / max(1, sum(new.values())),
            baseline_cost_per_correct=cost_b / max(1, sum(base.values())),
            benchmark=dict(n=len(bm), correct=sum(r["success"] for r in bm.values()),
                           sonnet_correct=sum(r["success"] for r in sonnet.values()),
                           vs_sonnet=paired({t: r["success"] for t, r in bm.items()},
                                            {t: r["success"] for t, r in sonnet.items()}, rng)))
    json.dump(out, open(os.path.join(HERE, "results.json"), "w"), indent=1)
    for m, o in out.items():
        v, b = o["vs_baseline"], o["benchmark"]
        print(f"{m:26} Kitaru replay {o['replay_correct']}/{o['n']} vs Sonnet baseline {o['baseline_correct']}/{o['n']}"
              f"  d {v['delta'] * 100:+.1f} [{v['lo'] * 100:+.1f}, {v['hi'] * 100:+.1f}]"
              f"  cost/correct {o['replay_cost_per_correct'] * 100:.2f}c vs {o['baseline_cost_per_correct'] * 100:.2f}c"
              f"  | benchmark same tasks {b['correct']}/{b['n']} vs Sonnet {b['sonnet_correct']}/{b['n']}"
              f"  d {b['vs_sonnet']['delta'] * 100:+.1f}")


if __name__ == "__main__":
    asyncio.run(main())
