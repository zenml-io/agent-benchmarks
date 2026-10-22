"""Memorization probe: can a model answer without the insurer's data, i.e. has it seen Snorkel's answers?

  python harness/probe.py [models...]

Snorkel's datasets (with reference answers) are public, so models trained after mid-2025 may have seen them. The
probe uses only tasks whose answer cannot be reasoned out (env/probe_tasks.json): small businesses that are out of
appetite purely because of the synthetic appetite table, and product recommendations whose in-appetite set is not
"all of them". Each model gets the full company profile and the question in one turn, with no tools and no data.
Without memorization it should almost never give the reference answer. Writes results/probe.json.
"""
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from judge import grade  # noqa: E402
from llm import complete  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODELS = ["opus-5.5", "sonnet-5.5", "haiku-5.5", "gpt-6.1-sol", "gpt-6-luna", "deepseek-v4-pro@provider-a",
          "deepseek-v4.1-flash@provider-a", "glm-5.3@provider-a", "glm-5.3-flash@provider-a", "gpt-oss-120b@provider-a",
          "qwen3.8-27b@provider-a", "minimax-m3@provider-a"]
SYSTEM = ("You are an underwriting assistant at All National Insurance, which writes commercial policies for small "
          "businesses in six lines of business: workers compensation, property, general liability, auto, cyber and "
          "bop. You have no tools or data access in this conversation; answer from what you know. Start your reply "
          "with 'FINAL ANSWER:' and give a definite answer.")
QUESTION = {
    "Appetite Check": "Is this company in appetite for the {lob} line of business?",
    "Product Recommendations": "Besides {lob}, which of our other lines of business are in appetite for this "
                               "company?",
}


def ask(model, t):
    c = t["company"]
    profile = (f"Company: {c['company name']}\nDescription: {c['company description']}\nState: {c['state']}\n"
               f"Annual revenue: ${int(c['annual revenue']):,}\nEmployees: {c['number of employees']}\n"
               f"Payroll: ${int(c['total payroll']):,}\nVehicles: {c['number of vehicles']}\n"
               f"Building construction: {c['building construction']}")
    q = QUESTION[t["task"]].format(lob=c["lob"])
    try:
        text, _, cost = complete(model, SYSTEM, [{"role": "user", "content": f"{profile}\n\n{q}"}], max_tokens=2000)
    except RuntimeError as e:
        return dict(task=t["id"], model=model, error=str(e)[:200], correct=None, cost=0.0)
    votes = [grade(j, t["task"], t["reference"], text) for j in ("gpt-6-luna", "haiku-5.5")]
    if votes[0][0] != votes[1][0]:
        votes.append(grade("gpt-6.1-sol", t["task"], t["reference"], text))
    return dict(task=t["id"], model=model, answer=text[:600], correct=votes[-1][0],
                cost=cost + sum(v[2] for v in votes))


def main():
    models = sys.argv[1:] or MODELS
    ids = set(json.load(open(os.path.join(ROOT, "env", "probe_tasks.json"))))
    tasks = [t for t in json.load(open(os.path.join(ROOT, "env", "tasks.json"))) if t["id"] in ids]
    jobs = [(m, t) for m in models for t in tasks]
    with ThreadPoolExecutor(16) as ex:
        res = list(ex.map(lambda mt: ask(*mt), jobs))
    out = {}
    for m in models:
        rs = [r for r in res if r["model"] == m and r["correct"] is not None]
        out[m] = dict(n=len(rs), correct=sum(r["correct"] for r in rs), rows=[r for r in res if r["model"] == m])
        print(f"{m:28} correct without data: {out[m]['correct']}/{out[m]['n']}", flush=True)
    print(f"cost ${sum(r['cost'] for r in res):.2f}")
    json.dump(out, open(os.path.join(ROOT, "results", "probe.json"), "w"), indent=1)


if __name__ == "__main__":
    main()
