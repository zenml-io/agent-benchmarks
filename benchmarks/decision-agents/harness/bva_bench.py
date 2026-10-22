"""
A veterans' disability appeals agent on real Board of Veterans' Appeals (BVA) decisions.

Each case is a single-issue appeal (e.g. service connection for hearing loss, an increased
rating, TDIU) that the Board either granted or denied. The agent gets a neutral evidence file
(service history, examinations, medical opinions, the veteran's statements; no Board findings
or conclusions) and structured tools, and must grant or deny. Same measurements as
claims_bench.py: accuracy vs baselines, rerun and model-change flips, replayability of tool
calls, citations, wrong decisions vs stated confidence and an LLM judge.

    python bva_bench.py build       # fetch decisions from va.gov (official text, public domain)
    python bva_bench.py all         # check servers, extract, run both models, judge
    python bva_bench.py analyze > bva.md

Case IDs come from a research index of BVA decisions on Hugging Face
(williamTLmiller/BVA-AMA-Era-170KStructured, CC-BY-NC-4.0, used for sampling and the
precedent library's labels); decision text and our labels come from the official files on
va.gov (the ORDER section).
"""

import argparse
import json
import random
import re
import statistics as st
import threading
import urllib.request
from collections import Counter, defaultdict

from claims_bench import MODELS, WORK, canon, chat, deploy, fn, jl, parallel, stop

D = WORK / "bva"
N_TEST, ATTEMPTS, MAX_TURNS = 150, 2, 12
LEAK = re.compile(r"\bthe board (finds|concludes|grants|denies|agrees)|is granted|is denied|warranted|"
                  r"not warranted|benefit of the doubt|reasonable doubt|preponderance|evenly balanced|"
                  r"criteria .{0,30}(are|have been) (met|not met)|finding of fact|conclusion of law", re.I)


# ---------------------------------------------------------------- data

def label_and_body(text):
    m = re.search(r"\bORDER\b(.*?)\b(FINDINGS? OF FACT)\b", text, re.S)
    if not m:
        return None, None
    order = m.group(1).lower()
    g, d = " granted" in order, " denied" in order
    if g == d or "remand" in order or "dismiss" in order:
        return None, None
    rb = re.search(r"REASONS AND BASES FOR FINDINGS? AND CONCLUSIONS?(.*)", text, re.S)
    return ("grant" if g else "deny"), (rb.group(1) if rb else None)


def build():
    D.mkdir(parents=True, exist_ok=True)
    idx = jl(D / "index_sample.jsonl")
    cand = [r for r in idx if r["outcomes"] in ("granted", "denied") and "|" not in str(r["issues"])
            and 3000 < int(r.get("char_length") or 0) < 25000]
    rng = random.Random(0)
    rng.shuffle(cand)

    def fetch(r):
        req = urllib.request.Request(r["source_url"], headers={"User-Agent": "agent-benchmarks decision-agents research (github.com/zenml-io/agent-benchmarks)"})
        text = urllib.request.urlopen(req, timeout=30).read().decode("utf-8", "replace")
        lab, body = label_and_body(text)
        return {"id": r["doc_id"], "issue": r["issues"], "conditions": r["conditions"], "truth": lab,
                "index_outcome": r["outcomes"], "body": (body or "")[:14000]} if lab and body else {"id": r["doc_id"], "skip": True}

    got = parallel(cand[:480], fetch, n=4)
    ok = [g for g in got if not g.get("skip") and g.get("truth")]
    agree = st.mean((g["truth"] == "grant") == (g["index_outcome"] == "granted") for g in ok)
    picked = []
    for lab in ("grant", "deny"):
        picked += rng.sample([g for g in ok if g["truth"] == lab], min(N_TEST, sum(g["truth"] == lab for g in ok)))
    test_ids = {g["id"] for g in picked}
    with (D / "candidates.jsonl").open("w") as f:
        for g in picked:
            f.write(json.dumps(g) + "\n")
    with (D / "precedents.jsonl").open("w") as f:  # the rest of the index sample, never a test case
        for r in idx:
            if r["doc_id"] not in test_ids and r["outcomes"] in ("granted", "denied") and "|" not in str(r["issues"]):
                f.write(json.dumps({"id": r["doc_id"], "decision": "grant" if r["outcomes"] == "granted" else "deny",
                                    "issue": r["issues"], "conditions": r["conditions"], "evidence": r["evidence"],
                                    "reasoning": r["reasoning_atoms"], "citations": (r["citations"] or "")[:400]}) + "\n")
    print(f"fetched {len(got)}, labelled {len(ok)} (our label agrees with the index {100 * agree:.0f}%), "
          f"candidates {len(picked)}", flush=True)


# ---------------------------------------------------------------- case files

EXTRACT = """You turn a Board of Veterans' Appeals decision into a neutral evidence file for a new
adjudicator. Keep ONLY the record: the issue on appeal, the veteran's service dates and duties,
what the veteran and others state, what each VA examination and private medical opinion found
or opined (with its date and author type), and relevant treatment records. Leave out everything
the Board concluded or argued: no findings, no weighing of evidence, no statements about
credibility, probative value, benefit of the doubt, whether criteria are met, or the outcome.
Write JSON only: {"issue": "...", "service": "...", "veteran_statements": ["..."],
"medical_evidence": ["..."], "other_evidence": ["..."]}."""


def extract(url):
    cands = jl(D / "candidates.jsonl")

    def one(c):
        r = chat(url, [{"role": "system", "content": EXTRACT}, {"role": "user", "content": f"Issue: {c['issue']}\n\n{c['body']}"}],
                 max_tokens=8000, temperature=0.0)
        text = r["choices"][0]["message"]["content"] or ""
        m = re.search(r"\{.*\}", text, re.S)
        try:
            cf = json.loads(m.group(0)) if m else None
        except json.JSONDecodeError:
            cf = None
        return {"id": c["id"], "case_file": cf, "leak": bool(LEAK.search(json.dumps(cf))) if cf else None}

    res = {r["id"]: r for r in parallel(cands, one) if r.get("id")}
    rng, cases = random.Random(1), []
    for lab in ("grant", "deny"):
        ok = [c for c in cands if c["truth"] == lab and res.get(c["id"], {}).get("case_file") and not res[c["id"]]["leak"]]
        for c in rng.sample(ok, min(len(ok), N_TEST // 2)):
            cases.append({k: v for k, v in c.items() if k != "body"} | {"case_file": res[c["id"]]["case_file"]})
    rng.shuffle(cases)
    with (D / "cases.jsonl").open("w") as f:
        for c in cases:
            f.write(json.dumps(c) + "\n")
    print(f"case files: {len(res)} extracted, {sum(1 for r in res.values() if r.get('leak'))} dropped for leaks, "
          f"{sum(1 for r in res.values() if not r.get('case_file'))} failed; kept {len(cases)}", flush=True)


# ---------------------------------------------------------------- agent

SYSTEM = """You are an adjudicator reviewing a veteran's appeal of a VA disability decision. Decide
whether the benefit sought should be GRANTED or DENIED based on the evidence of record, applying
VA's standards (including that reasonable doubt is resolved in the veteran's favor). Use the tools
to read the appeal and the evidence and to look up how similar past appeals were decided, then
call submit_decision exactly once. Cite only decision IDs you actually retrieved."""

TOOLS = [
    fn("get_appeal", "The issue on appeal and the veteran's service.", {"case_id": {"type": "string"}}, ["case_id"]),
    fn("get_evidence", "Statements, medical evidence and other evidence of record.", {"case_id": {"type": "string"}}, ["case_id"]),
    fn("search_decisions", "Past Board decisions (2019-2026) whose issue mentions a keyword, e.g. 'tinnitus' or 'TDIU'.",
       {"keyword": {"type": "string"}, "outcome": {"type": "string", "enum": ["grant", "deny"], "description": "optional"}},
       ["keyword"]),
    fn("get_decision", "Details of one past decision: issue, outcome, kinds of evidence and reasoning, citations.",
       {"decision_id": {"type": "string"}}, ["decision_id"]),
    fn("submit_decision", "Final answer.",
       {"decision": {"type": "string", "enum": ["grant", "deny"]},
        "confidence": {"type": "string", "enum": ["low", "medium", "high"]},
        "rationale": {"type": "string"},
        "cited_decisions": {"type": "array", "items": {"type": "string"}}},
       ["decision", "confidence", "rationale", "cited_decisions"]),
]


class Env:
    def __init__(self):
        self.cases = {c["id"]: c for c in jl(D / "cases.jsonl")}
        self.prec = {p["id"]: p for p in jl(D / "precedents.jsonl")}

    def call(self, case_id, name, a):
        c, cf = self.cases[case_id], self.cases[case_id]["case_file"]
        if name == "get_appeal":
            return {"case_id": case_id, "issue": cf.get("issue") or c["issue"], "service": cf.get("service")}
        if name == "get_evidence":
            return {k: cf.get(k) for k in ("veteran_statements", "medical_evidence", "other_evidence")}
        if name == "search_decisions":
            kw = str(a.get("keyword", "")).lower().strip()
            hits = [p for p in self.prec.values() if kw and kw in str(p["issue"]).lower()]
            if a.get("outcome") in ("grant", "deny"):
                hits = [p for p in hits if p["decision"] == a["outcome"]]
            hits.sort(key=lambda p: p["id"], reverse=True)
            return {"total_matches": len(hits), "results": [{"decision_id": p["id"], "outcome": p["decision"],
                                                             "issue": str(p["issue"])[:300]} for p in hits[:5]]}
        if name == "get_decision":
            p = self.prec.get(str(a.get("decision_id")))
            return p if p else {"error": "not found"}
        return {"error": f"unknown tool {name}"}


def session(url, env, case_id, model, attempt):
    msgs = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": f"Review appeal {case_id}."}]
    calls, seen, final = [], set(), None
    for turn in range(MAX_TURNS):
        r = chat(url, msgs, tools=TOOLS)
        m = r["choices"][0]["message"]
        tc = m.get("tool_calls") or []
        msgs.append({"role": "assistant", "content": m.get("content") or "", **({"tool_calls": tc} if tc else {})})
        if not tc:
            msgs.append({"role": "user", "content": "Use the tools, and finish with submit_decision."})
            continue
        for c in tc:
            name = c["function"]["name"]
            try:
                a = json.loads(c["function"]["arguments"] or "{}")
            except json.JSONDecodeError:
                a = {}
            calls.append({"name": name, "args": a})
            if name == "submit_decision":
                final = a
                break
            out = env.call(case_id, name, a)
            for x in out.get("results", []) if isinstance(out, dict) else []:
                seen.add(str(x["decision_id"]))
            if name == "get_decision" and isinstance(out, dict) and out.get("id"):
                seen.add(out["id"])
            msgs.append({"role": "tool", "tool_call_id": c["id"], "content": json.dumps(out)[:6000]})
        if final:
            break
    return {"case_id": case_id, "model": model, "attempt": attempt, "final": final, "calls": calls,
            "seen": sorted(seen), "turns": turn + 1, "transcript": msgs}


def run(url, model):
    env = Env()
    out = parallel([(c, a) for a in range(ATTEMPTS) for c in env.cases], lambda j: session(url, env, j[0], model, j[1]))
    with (D / f"sessions_{model}.jsonl").open("w") as f:
        for s in out:
            f.write(json.dumps(s) + "\n")
    print(f"{model}: {len(out)} sessions, {sum(1 for s in out if s.get('final'))} with a decision", flush=True)


JUDGE = """You audit an AI adjudicator of veterans' disability appeals. Below is its full working: the
appeal, the evidence and past decisions it looked at, and its final decision. The Board of
Veterans' Appeals decided these appeals. Judge whether the AI's decision (grant or deny) is the
correct one. Answer JSON only: {"verdict": "correct" | "incorrect", "confidence": 0-100}"""


def judge(url):
    def one(s):
        work = []
        for m in s["transcript"][1:]:
            if m["role"] == "tool":
                work.append(f"[tool result] {m['content'][:1500]}")
            elif m["role"] == "assistant" and m.get("tool_calls"):
                work.append("[calls] " + "; ".join(f"{c['function']['name']}({c['function']['arguments']})" for c in m["tool_calls"]))
        r = chat(url, [{"role": "system", "content": JUDGE}, {"role": "user", "content": "\n".join(work)[:24000]}],
                 max_tokens=16000, temperature=0.0)
        m = re.search(r"\{[^{}]*\"verdict\"[^{}]*\}", r["choices"][0]["message"]["content"] or "", re.S)
        try:
            v = json.loads(m.group(0)) if m else {}
        except json.JSONDecodeError:
            v = {}
        return {"case_id": s["case_id"], "model": s["model"], "attempt": s["attempt"], "verdict": v.get("verdict")}

    partial, lock = D / "judgments.partial.jsonl", threading.Lock()
    done = {(j["case_id"], j["model"], j["attempt"]): j for j in jl(D / "judgments.jsonl") + jl(partial)
            if j.get("case_id") and j.get("verdict")}

    def keep(s):  # save each verdict as it arrives, so a restart loses nothing
        j = one(s)
        if j.get("verdict"):
            with lock, partial.open("a") as f:
                f.write(json.dumps(j) + "\n")
        return j

    sess = [s for m in MODELS for s in jl(D / f"sessions_{m}.jsonl")
            if s.get("final") and (s["case_id"], s["model"], s["attempt"]) not in done]
    out = list(done.values()) + parallel(sess, keep)
    with (D / "judgments.jsonl").open("w") as f:
        for j in out:
            f.write(json.dumps(j) + "\n")
    print(f"judge: {len(out)} verdicts", flush=True)


# ---------------------------------------------------------------- analysis

def analyze():
    cases = {c["id"]: c for c in jl(D / "cases.jsonl")}
    prec = list(jl(D / "precedents.jsonl"))
    S = {m: [s for s in jl(D / f"sessions_{m}.jsonl") if s.get("case_id") in cases] for m in MODELS}
    J = {(j["case_id"], j["model"], j["attempt"]): j.get("verdict") for j in jl(D / "judgments.jsonl") if j.get("case_id")}
    pct = lambda x: f"{100 * x:.0f}%"  # noqa: E731
    dec = lambda s: (s.get("final") or {}).get("decision")  # noqa: E731
    grant_rate = st.mean(p["decision"] == "grant" for p in prec)

    def kw_baseline(c):  # majority outcome of past decisions sharing the issue's first condition word
        words = [w for w in re.findall(r"[a-z]{5,}", str(c["issue"]).lower())
                 if w not in ("entitlement", "service", "connection", "rating", "disability", "excess", "percent", "increased")]
        for w in words:
            hits = Counter(p["decision"] for p in prec if w in str(p["issue"]).lower())
            if sum(hits.values()) >= 5:
                return hits.most_common(1)[0][0]
        return "grant" if grant_rate >= 0.5 else "deny"

    base = st.mean(kw_baseline(c) == c["truth"] for c in cases.values())
    L = ["# A veterans' appeals agent on real Board decisions", "",
         f"{len(cases)} single-issue BVA appeals (half granted, half denied), labels from each decision's ORDER; "
         f"{len(prec)} other decisions as a searchable library. {ATTEMPTS} attempts per case and model.", "",
         "## 1. Accuracy", "", "| who decides | accuracy | no decision |", "|---|---|---|",
         "| always 'grant' | 50% | |", f"| majority of past decisions on the same condition (no AI) | {pct(base)} | |"]
    for m, ss in S.items():
        d = [s for s in ss if dec(s)]
        L.append(f"| agent, {m} model | {pct(st.mean(dec(s) == cases[s['case_id']]['truth'] for s in d))} (n={len(d)}) | "
                 f"{len(ss) - len(d)} of {len(ss)} |")
    D_ = {(s["case_id"], s["model"], s["attempt"]): s for ss in S.values() for s in ss}
    L += ["", "## 2. Flips", "", "| comparison | pairs | decision differs |", "|---|---|---|"]
    for m in MODELS:
        p = [(dec(D_[(c, m, 0)]), dec(D_[(c, m, 1)])) for c in cases if (c, m, 0) in D_ and (c, m, 1) in D_]
        p = [x for x in p if None not in x]
        if p:
            L.append(f"| rerun, {m} model | {len(p)} | {pct(st.mean(a != b for a, b in p))} |")
    p = [(dec(D_[(c, "dense", a)]), dec(D_[(c, "moe", a)])) for c in cases for a in range(ATTEMPTS)
         if (c, "dense", a) in D_ and (c, "moe", a) in D_]
    p = [x for x in p if None not in x]
    if p:
        L.append(f"| model change | {len(p)} | {pct(st.mean(a != b for a, b in p))} |")
    L += ["", "## 3. Replay from recorded tool answers", "",
          "| comparison | pairs | identical call sequence | new run's calls found in the recorded run | runs fully answerable |",
          "|---|---|---|---|---|"]
    calls = {k: [canon(c) for c in s["calls"] if c["name"] != "submit_decision"] for k, s in D_.items() if s.get("calls")}

    def rep(label, pairs):
        pairs = [(a, b) for a, b in pairs if a and b]
        if pairs:
            cov = [sum(x in set(a) for x in b) / len(b) for a, b in pairs]
            L.append(f"| {label} | {len(pairs)} | {pct(st.mean(a == b for a, b in pairs))} | {pct(st.mean(cov))} | "
                     f"{pct(st.mean(c == 1 for c in cov))} |")
    for m in MODELS:
        rep(f"rerun, {m}", [(calls.get((c, m, 0)), calls.get((c, m, 1))) for c in cases])
    rep("model change", [(calls.get((c, "dense", a)), calls.get((c, "moe", a))) for c in cases for a in range(ATTEMPTS)])
    rows = []
    for k, s in D_.items():
        if dec(s):
            other = D_.get((k[0], "moe" if k[1] == "dense" else "dense", k[2]))
            rows.append({"right": dec(s) == cases[k[0]]["truth"], "conf": s["final"].get("confidence"), "decision": dec(s),
                         "judge": J.get(k), "xmodel": other is not None and dec(other) not in (None, dec(s)),
                         "unseen_cite": any(str(x) not in s["seen"] for x in (s["final"].get("cited_decisions") or []))})
    if rows:
        wrong, right = [r for r in rows if not r["right"]], [r for r in rows if r["right"]]
        f = lambda key, val=True: (pct(st.mean(r[key] == val for r in wrong)), pct(st.mean(r[key] == val for r in right)))  # noqa: E731
        jr = [r for r in rows if r["judge"] in ("correct", "incorrect")]
        L += ["", "## 4. Wrong decisions", "",
              f"- Wrong: {len(wrong)} of {len(rows)} ({pct(len(wrong) / len(rows))}); wrongful denials "
              f"{sum(r['decision'] == 'deny' for r in wrong)}, wrongful grants {sum(r['decision'] == 'grant' for r in wrong)}.",
              f"- Cites a decision it never retrieved: {pct(st.mean(r['unseen_cite'] for r in rows))} of decisions.",
              "", "| signal | catches wrong decisions | flags right ones |", "|---|---|---|",
              "| not stated with high confidence | %s | %s |" % tuple(pct(st.mean(r['conf'] != 'high' for r in g)) for g in (wrong, right)),
              "| the other model disagrees | %s | %s |" % f("xmodel")]
        if jr:
            jw, jrr = [r for r in jr if not r["right"]], [r for r in jr if r["right"]]
            L.append(f"| LLM judge says incorrect ({len(jr)} judged) | {pct(st.mean(r['judge'] == 'incorrect' for r in jw)) if jw else 'n/a'} | "
                     f"{pct(st.mean(r['judge'] == 'incorrect' for r in jrr)) if jrr else 'n/a'} |")
    print("\n".join(L))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["build", "all", "analyze", "judge"])
    a = ap.parse_args()
    if a.cmd == "build":
        build()
    elif a.cmd == "analyze":
        analyze()
    elif a.cmd == "judge":  # judge sessions that have no verdict yet
        url, _ = deploy("bva-dense", MODELS["dense"])
        try:
            judge(url)
        finally:
            stop("bva-dense")
    else:
        url, _ = deploy("bva-dense", MODELS["dense"])
        try:
            if not (D / "cases.jsonl").exists():
                extract(url)
            moe = {}

            def bring_up_moe():
                try:
                    moe["url"], _ = deploy("bva-moe", MODELS["moe"])
                    run(moe["url"], "moe")
                finally:
                    stop("bva-moe")

            t = threading.Thread(target=bring_up_moe)
            t.start()
            run(url, "dense")
            t.join()
            judge(url)
        finally:
            stop("bva-dense")
            stop("bva-moe")


if __name__ == "__main__":
    main()
