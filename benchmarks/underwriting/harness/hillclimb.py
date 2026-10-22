"""Tune the system prompt per model on the learning split, then score the best prompt once on the held-out split.

  python harness/hillclimb.py <model> [--rounds 2]

The loop follows the train/test discipline of eval hill-climbing: the optimizer (Claude Opus 5.5) reads the model's
failures on the learning cases (env/split.json "learn") and rewrites the system prompt with general instructions;
the rewrite is kept only when the learning score improves. It never sees the held-out cases. A rewrite that copies
case facts (numbers, company names) into the prompt is rejected, since that tunes the prompt to the cases it is
judged on. Round 0 is the benchmark's own run on the learning cases. The best prompt is then run once on the
held-out cases (arm "tuned"); when no rewrite helped, the held-out arm is skipped and the baseline stands.
Writes results/tuned/prompts/<model>/v<round>.txt and results/tuned/hillclimb/<model>.json.
"""
import argparse
import json
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import run as H  # noqa: E402
from llm import complete  # noqa: E402

ROOT = H.ROOT
OPTIMIZER = "opus-5.5"
MAX_FAILURES = 12
OPTIMIZER_SYSTEM = """You improve the system prompt of an AI underwriting copilot. The copilot helps a commercial \
insurance underwriter with questions about small-business applications (appetite for a line of business, other \
products to offer, small-business eligibility, policy limits, deductibles, NAICS classification). It has tools over \
the insurer's database and guidelines, and it talks to the underwriter, who holds the application details.

You get the current prompt and failed cases from a set of learning cases, each with the conversation, the \
copilot's final answer, the reference answer, and the grader's reason. Find the causes that recur across cases \
(how the copilot gathers information, uses the tools, applies the guidelines, or ends the conversation) and rewrite \
the prompt to fix them.

Rules:
- Write general instructions. Never copy facts from the cases into the prompt: no NAICS codes, numbers, company \
names, states, table values, or which business is in or out of appetite. The prompt will be tested on cases you \
have not seen, so a prompt that encodes these answers fails.
- Keep everything the current prompt needs, including the exact "FINAL ANSWER:" convention.
- Prefer fixing a root cause over adding a special case. Remove instructions that cause failures.

Reply with the full new prompt between <prompt> and </prompt>, then one short paragraph on what you changed and why."""


def load_rows(path):
    rows = {}
    if os.path.exists(path):
        for line in open(path):
            r = json.loads(line)
            if r["status"] != "harness_error":
                rows[r["task"]] = r
    return rows


def failures_text(model, rows, transcripts_dir, tasks):
    out = []
    failed = [r for r in rows.values() if not r["success"]][:MAX_FAILURES]
    for r in failed:
        path = os.path.join(transcripts_dir, f"{r['task']}.json")
        convo = ""
        if os.path.exists(path):
            tr = json.load(open(path))["transcript"]
            convo = "\n".join(f"{who}: {text[:600]}" for who, text in tr[-8:])
        verdict = (r.get("verdicts") or [[None, None, ""]])[-1]
        out.append(f"<case type=\"{r['task_type']}\" status=\"{r['status']}\" tool_calls=\"{r.get('tool_calls')}\">\n"
                   f"{convo}\nFINAL: {(r.get('final_answer') or '(none)')[:500]}\n"
                   f"REFERENCE: {tasks[r['task']]['reference'][:400]}\nGRADER: {str(verdict[2])[:300]}\n</case>")
    return "\n\n".join(out), len(failed)


def leaks(prompt, base, learn_tasks):
    """Facts copied from the cases: numbers absent from the base prompt, or company names."""
    nums = set(re.findall(r"\b\d{3,}\b", prompt)) - set(re.findall(r"\b\d{3,}\b", base))
    names = [t["company"]["company name"] for t in learn_tasks
             if t["company"]["company name"].lower() in prompt.lower()]
    return sorted(nums) + names


def run_arm(model, arm, prompt_file, split):
    cmd = [sys.executable, os.path.join(ROOT, "harness", "run.py"), model, "--arm", arm, "--split", split,
           "--prompt", prompt_file, "--workers", "8"]
    subprocess.run(cmd, check=True, env={**os.environ, "PYTHONHASHSEED": "0"})
    return load_rows(os.path.join(ROOT, "results", "tuned", "runs", f"{model}__{arm}.jsonl"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("model")
    ap.add_argument("--rounds", type=int, default=2)
    a = ap.parse_args()
    tasks = {t["id"]: t for t in json.load(open(os.path.join(H.ENV, "tasks.json")))}
    split = json.load(open(os.path.join(H.ENV, "split.json")))
    learn = set(split["learn"])
    pdir = os.path.join(ROOT, "results", "tuned", "prompts", a.model)
    os.makedirs(pdir, exist_ok=True)
    os.makedirs(os.path.join(ROOT, "results", "tuned", "hillclimb"), exist_ok=True)
    base_prompt = H.SYSTEM
    open(os.path.join(pdir, "v0.txt"), "w").write(base_prompt)
    rows = {k: v for k, v in load_rows(os.path.join(ROOT, "results", "runs", f"{a.model}.jsonl")).items() if k in learn}
    tdir = os.path.join(ROOT, "results", "transcripts", a.model)
    log = dict(model=a.model, rounds=[dict(round=0, learn_correct=sum(r["success"] for r in rows.values()),
                                           learn_n=len(rows), kept=True)], optimizer_cost=0.0)
    best = dict(round=0, prompt=base_prompt, correct=log["rounds"][0]["learn_correct"], rows=rows, tdir=tdir)
    print(f"{a.model} round 0: {best['correct']}/{len(rows)} on learning cases", flush=True)
    for rnd in range(1, a.rounds + 1):
        text, n_failed = failures_text(a.model, best["rows"], best["tdir"], tasks)
        if not n_failed:
            break
        prompt = None
        for _attempt in range(2):
            reply, _, cost = complete(OPTIMIZER, OPTIMIZER_SYSTEM, [{"role": "user", "content":
                                      f"<current_prompt>\n{best['prompt']}\n</current_prompt>\n\n"
                                      f"{n_failed} failed learning cases:\n\n{text}"}], max_tokens=6000)
            log["optimizer_cost"] += cost
            m = re.search(r"<prompt>\s*(.*?)\s*</prompt>", reply, re.S)
            if not m:
                continue
            found = leaks(m.group(1), base_prompt, [tasks[t] for t in learn])
            if found:
                print(f"  rejected a rewrite that copies case facts: {found[:5]}", flush=True)
                continue
            prompt, why = m.group(1), reply[m.end():].strip()[:1000]
            break
        if prompt is None:
            log["rounds"].append(dict(round=rnd, error="no usable rewrite"))
            break
        path = os.path.join(pdir, f"v{rnd}.txt")
        open(path, "w").write(prompt)
        rows = run_arm(a.model, f"tune{rnd}", path, "learn")
        correct = sum(r["success"] for r in rows.values())
        kept = correct > best["correct"]
        log["rounds"].append(dict(round=rnd, learn_correct=correct, learn_n=len(rows), kept=kept, why=why))
        print(f"{a.model} round {rnd}: {correct}/{len(rows)} ({'kept' if kept else 'reverted'})", flush=True)
        if kept:
            best = dict(round=rnd, prompt=prompt, correct=correct, rows=rows,
                        tdir=os.path.join(ROOT, "results", "tuned", "transcripts", f"{a.model}__tune{rnd}"))
    log["best_round"] = best["round"]
    if best["round"]:
        held = run_arm(a.model, "tuned", os.path.join(pdir, f"v{best['round']}.txt"), "held")
        log["held_correct"], log["held_n"] = sum(r["success"] for r in held.values()), len(held)
        print(f"{a.model} tuned prompt v{best['round']} on held-out: {log['held_correct']}/{log['held_n']}", flush=True)
    json.dump(log, open(os.path.join(ROOT, "results", "tuned", "hillclimb", f"{a.model}.json"), "w"), indent=1)
    print(f"optimizer ${log['optimizer_cost']:.2f}", flush=True)


if __name__ == "__main__":
    main()
