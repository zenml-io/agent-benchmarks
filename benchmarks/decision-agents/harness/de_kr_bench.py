"""
A German health-insurance dispute agent on real social court decisions (Sozialgericht, first
instance, register "KR": a statutory health insurer refused a benefit and the insured sued).

The agent reads the court's own statement of facts (Tatbestand: the dispute, the history, the
medical evidence and both sides' applications; German judgments keep the reasoning in a separate
section) and must decide: dismiss the claim (the insurer's refusal stands) or allow it. Labels
come from each judgment's operative ruling (Tenor). Same measurements as claims_bench.py.

    python de_kr_fetch.py           # collect cases from the Open Legal Data API
    python de_kr_bench.py all       # check servers, run both models, judge
    python de_kr_bench.py analyze > de_kr.md
"""

import argparse
import json
import random
import re
import statistics as st
import threading
from collections import Counter

from claims_bench import MODELS, WORK, canon, chat, deploy, fn, jl, parallel, stop

D = WORK / "de_kr"
N_TEST, ATTEMPTS, MAX_TURNS = 150, 2, 12


def split_cases():
    raw = jl(D / "cases_raw.jsonl")
    rng = random.Random(0)
    by = {lab: [r for r in raw if r["truth"] == lab] for lab in ("uphold", "overturn")}
    k = min(N_TEST // 2, *(len(v) for v in by.values()))
    test = [r for lab in by for r in rng.sample(by[lab], k)]
    ids = {r["id"] for r in test}
    rng.shuffle(test)
    return test, [r for r in raw if r["id"] not in ids]


def first_para(facts):
    return re.sub(r"\s+", " ", re.sub(r"^\s*\d+\s*", "", facts.strip()))[:600]


SYSTEM = """Sie sind Richterin oder Richter am Sozialgericht. Eine gesetzlich versicherte Person klagt
gegen ihre Krankenkasse, die eine Leistung abgelehnt hat. Entscheiden Sie anhand des Tatbestands,
ob die Klage ABGEWIESEN wird (die Ablehnung der Krankenkasse bleibt bestehen) oder ob ihr
STATTGEGEBEN wird (die Krankenkasse muss leisten). Nutzen Sie die Werkzeuge, um den Fall und die
Akte zu lesen und frühere Entscheidungen zu ähnlichen Fragen nachzuschlagen, und rufen Sie dann
genau einmal submit_entscheidung auf. Zitieren Sie nur Entscheidungen, die Sie tatsächlich abgerufen haben."""

TOOLS = [
    fn("get_fall", "Streitgegenstand und Gericht.", {"case_id": {"type": "string"}}, ["case_id"]),
    fn("get_akte", "Der vollständige Tatbestand: Vorgeschichte, medizinische Unterlagen, Gutachten, Anträge.",
       {"case_id": {"type": "string"}}, ["case_id"]),
    fn("suche_entscheidungen", "Frühere Sozialgerichtsentscheidungen (KR), deren Tatbestand ein Stichwort enthält, "
       "z.B. 'Liposuktion' oder 'Cannabis'.",
       {"stichwort": {"type": "string"}, "ergebnis": {"type": "string", "enum": ["abgewiesen", "stattgegeben"],
                                                     "description": "optional"}}, ["stichwort"]),
    fn("get_entscheidung", "Ergebnis und Tatbestand einer früheren Entscheidung.", {"entscheidung_id": {"type": "string"}},
       ["entscheidung_id"]),
    fn("submit_entscheidung", "Endgültige Entscheidung.",
       {"entscheidung": {"type": "string", "enum": ["abweisen", "stattgeben"]},
        "sicherheit": {"type": "string", "enum": ["niedrig", "mittel", "hoch"]},
        "begruendung": {"type": "string"},
        "zitierte_entscheidungen": {"type": "array", "items": {"type": "string"}}},
       ["entscheidung", "sicherheit", "begruendung", "zitierte_entscheidungen"]),
]
OUT = {"abgewiesen": "uphold", "stattgegeben": "overturn"}


class Env:
    def __init__(self):
        test, pool = split_cases()
        self.cases = {str(c["id"]): c for c in test}
        self.prec = {str(p["id"]): p for p in pool}

    def call(self, cid, name, a):
        c = self.cases[cid]
        if name == "get_fall":
            return {"case_id": cid, "gericht": c["court"], "streitgegenstand": first_para(c["facts"])}
        if name == "get_akte":
            return {"tatbestand": c["facts"][:12000]}
        if name == "suche_entscheidungen":
            kw = str(a.get("stichwort", "")).lower().strip()
            hits = [p for p in self.prec.values() if kw and kw in p["facts"].lower()]
            if a.get("ergebnis") in OUT:
                hits = [p for p in hits if p["truth"] == OUT[a["ergebnis"]]]
            hits.sort(key=lambda p: p["date"], reverse=True)
            return {"treffer": len(hits), "ergebnisse": [
                {"entscheidung_id": str(p["id"]), "gericht": p["court"], "datum": p["date"],
                 "ergebnis": "abgewiesen" if p["truth"] == "uphold" else "stattgegeben",
                 "streitgegenstand": first_para(p["facts"])[:300]} for p in hits[:5]]}
        if name == "get_entscheidung":
            p = self.prec.get(str(a.get("entscheidung_id")))
            if not p:
                return {"error": "nicht gefunden"}
            return {"entscheidung_id": str(p["id"]), "gericht": p["court"], "datum": p["date"],
                    "ergebnis": "abgewiesen" if p["truth"] == "uphold" else "stattgegeben", "tatbestand": p["facts"][:3000]}
        return {"error": f"unbekanntes Werkzeug {name}"}


def session(url, env, cid, model, attempt):
    msgs = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": f"Entscheiden Sie den Fall {cid}."}]
    calls, seen, final = [], set(), None
    for turn in range(MAX_TURNS):
        r = chat(url, msgs, tools=TOOLS)
        m = r["choices"][0]["message"]
        tc = m.get("tool_calls") or []
        msgs.append({"role": "assistant", "content": m.get("content") or "", **({"tool_calls": tc} if tc else {})})
        if not tc:
            msgs.append({"role": "user", "content": "Nutzen Sie die Werkzeuge und schließen Sie mit submit_entscheidung ab."})
            continue
        for c in tc:
            name = c["function"]["name"]
            try:
                a = json.loads(c["function"]["arguments"] or "{}")
            except json.JSONDecodeError:
                a = {}
            calls.append({"name": name, "args": a})
            if name == "submit_entscheidung":
                final = a
                break
            out = env.call(cid, name, a)
            for x in out.get("ergebnisse", []) if isinstance(out, dict) else []:
                seen.add(x["entscheidung_id"])
            if name == "get_entscheidung" and isinstance(out, dict) and out.get("entscheidung_id"):
                seen.add(out["entscheidung_id"])
            msgs.append({"role": "tool", "tool_call_id": c["id"], "content": json.dumps(out, ensure_ascii=False)[:8000]})
        if final:
            break
    dec = {"abweisen": "uphold", "stattgeben": "overturn"}.get((final or {}).get("entscheidung"))
    return {"case_id": cid, "model": model, "attempt": attempt, "final": final, "decision": dec, "calls": calls,
            "seen": sorted(seen), "turns": turn + 1, "transcript": msgs}


def run(url, model):
    env = Env()
    out = parallel([(c, a) for a in range(ATTEMPTS) for c in env.cases], lambda j: session(url, env, j[0], model, j[1]))
    with (D / f"sessions_{model}.jsonl").open("w") as f:
        for s in out:
            f.write(json.dumps(s, ensure_ascii=False) + "\n")
    print(f"{model}: {len(out)} sessions, {sum(1 for s in out if s.get('decision'))} with a decision", flush=True)


JUDGE = """Sie prüfen die Arbeit einer KI, die sozialgerichtliche Streitigkeiten mit Krankenkassen
entscheidet. Unten steht ihre vollständige Arbeit: der Fall, die Akte, die herangezogenen früheren
Entscheidungen und ihre Entscheidung. Die Fälle wurden von Sozialgerichten entschieden. Beurteilen Sie,
ob die Entscheidung der KI (abweisen oder stattgeben) richtig ist. Antworten Sie nur mit JSON:
{"urteil": "richtig" | "falsch", "sicherheit": 0-100}"""


def judge(url):
    def one(s):
        work = []
        for m in s["transcript"][1:]:
            if m["role"] == "tool":
                work.append(f"[Werkzeug] {m['content'][:2000]}")
            elif m["role"] == "assistant" and m.get("tool_calls"):
                work.append("[Aufrufe] " + "; ".join(f"{c['function']['name']}({c['function']['arguments']})" for c in m["tool_calls"]))
        r = chat(url, [{"role": "system", "content": JUDGE}, {"role": "user", "content": "\n".join(work)[:24000]}],
                 max_tokens=16000, temperature=0.0)
        m = re.search(r"\{[^{}]*\"urteil\"[^{}]*\}", r["choices"][0]["message"]["content"] or "", re.S)
        try:
            v = json.loads(m.group(0)) if m else {}
        except json.JSONDecodeError:
            v = {}
        return {"case_id": s["case_id"], "model": s["model"], "attempt": s["attempt"],
                "verdict": {"richtig": "correct", "falsch": "incorrect"}.get(v.get("urteil"))}

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
            if s.get("decision") and (s["case_id"], s["model"], s["attempt"]) not in done]
    out = list(done.values()) + parallel(sess, keep)
    with (D / "judgments.jsonl").open("w") as f:
        for j in out:
            f.write(json.dumps(j) + "\n")
    print(f"judge: {len(out)} verdicts", flush=True)


def analyze():
    env = Env()
    cases, prec = env.cases, list(env.prec.values())
    S = {m: [s for s in jl(D / f"sessions_{m}.jsonl") if s.get("case_id") in cases] for m in MODELS}
    J = {(j["case_id"], j["model"], j["attempt"]): j.get("verdict") for j in jl(D / "judgments.jsonl") if j.get("case_id")}
    pct = lambda x: f"{100 * x:.0f}%"  # noqa: E731
    base_rate = Counter(p["truth"] for p in prec).most_common(1)[0][0]

    def kw_baseline(c):  # majority outcome of library cases sharing a distinctive word of the dispute
        words = sorted(set(re.findall(r"[a-zäöüß]{9,}", first_para(c["facts"]).lower())), key=len, reverse=True)
        for w in words:
            hits = Counter(p["truth"] for p in prec if w in p["facts"].lower())
            if 5 <= sum(hits.values()) <= 200:
                return hits.most_common(1)[0][0]
        return base_rate

    L = ["# A German health-insurance dispute agent on real social court decisions", "",
         f"{len(cases)} first-instance KR judgments (half dismissed, half allowed), labels from each Tenor; "
         f"{len(prec)} other judgments as a searchable library (base rate in the library: "
         f"{pct(st.mean(p['truth'] == 'uphold' for p in prec))} dismissed). {ATTEMPTS} attempts per case and model.", "",
         "## 1. Accuracy", "", "| who decides | accuracy | no decision |", "|---|---|---|",
         "| always 'dismiss' | 50% | |",
         f"| majority of library cases sharing a word of the dispute (no AI) | {pct(st.mean(kw_baseline(c) == c['truth'] for c in cases.values()))} | |"]
    for m, ss in S.items():
        d = [s for s in ss if s.get("decision")]
        if d:
            L.append(f"| agent, {m} model | {pct(st.mean(s['decision'] == cases[s['case_id']]['truth'] for s in d))} (n={len(d)}) | "
                     f"{len(ss) - len(d)} of {len(ss)} |")
    X = {(s["case_id"], s["model"], s["attempt"]): s for ss in S.values() for s in ss}
    dec = lambda k: (X.get(k) or {}).get("decision")  # noqa: E731
    L += ["", "## 2. Flips", "", "| comparison | pairs | decision differs |", "|---|---|---|"]
    for label, pairs in [(f"rerun, {m} model", [((c, m, 0), (c, m, 1)) for c in cases]) for m in MODELS] + \
                        [("model change", [((c, "dense", a), (c, "moe", a)) for c in cases for a in range(ATTEMPTS)])]:
        p = [(dec(a), dec(b)) for a, b in pairs if dec(a) and dec(b)]
        if p:
            L.append(f"| {label} | {len(p)} | {pct(st.mean(x != y for x, y in p))} |")
    calls = {k: [canon(c) for c in s["calls"] if c["name"] != "submit_entscheidung"] for k, s in X.items()}
    L += ["", "## 3. Replay from recorded tool answers", "",
          "| comparison | pairs | new run's calls found in the recorded run | runs fully answerable |", "|---|---|---|---|"]
    for label, pairs in [(f"rerun, {m}", [((c, m, 0), (c, m, 1)) for c in cases]) for m in MODELS] + \
                        [("model change", [((c, "dense", a), (c, "moe", a)) for c in cases for a in range(ATTEMPTS)])]:
        pr = [(calls.get(a), calls.get(b)) for a, b in pairs if calls.get(a) and calls.get(b)]
        if pr:
            cov = [sum(x in set(a) for x in b) / len(b) for a, b in pr]
            L.append(f"| {label} | {len(pr)} | {pct(st.mean(cov))} | {pct(st.mean(c == 1 for c in cov))} |")
    rows = []
    for k, s in X.items():
        if s.get("decision"):
            o = X.get((k[0], "moe" if k[1] == "dense" else "dense", k[2]))
            rows.append({"right": s["decision"] == cases[k[0]]["truth"], "hoch": s["final"].get("sicherheit") == "hoch",
                         "x": bool(o and o.get("decision") and o["decision"] != s["decision"]), "judge": J.get(k),
                         "dec": s["decision"],
                         "unseen": any(str(x) not in s["seen"] for x in (s["final"].get("zitierte_entscheidungen") or []))})
    if rows:
        w, r = [x for x in rows if not x["right"]], [x for x in rows if x["right"]]
        jw = [x for x in w if x["judge"] in ("correct", "incorrect")]
        jr = [x for x in r if x["judge"] in ("correct", "incorrect")]
        L += ["", "## 4. Wrong decisions", "",
              f"- Wrong: {len(w)} of {len(rows)} ({pct(len(w) / len(rows))}); claims wrongly dismissed "
              f"{sum(x['dec'] == 'uphold' for x in w)}, wrongly allowed {sum(x['dec'] == 'overturn' for x in w)}.",
              f"- Cites a decision it never retrieved: {pct(st.mean(x['unseen'] for x in rows))}.", "",
              "| signal | catches wrong decisions | flags right ones |", "|---|---|---|",
              f"| not stated with high confidence | {pct(st.mean(not x['hoch'] for x in w))} | {pct(st.mean(not x['hoch'] for x in r))} |",
              f"| the other model disagrees | {pct(st.mean(x['x'] for x in w))} | {pct(st.mean(x['x'] for x in r))} |"]
        if jw and jr:
            L.append(f"| LLM judge says wrong ({len(jw) + len(jr)} judged) | {pct(st.mean(x['judge'] == 'incorrect' for x in jw))} | "
                     f"{pct(st.mean(x['judge'] == 'incorrect' for x in jr))} |")
    print("\n".join(L))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["all", "analyze", "resume"])
    a = ap.parse_args()
    if a.cmd == "analyze":
        analyze()
        return
    if a.cmd == "resume":  # rerun sessions that crashed on server errors (e.g. HTTP 503), then judge the new ones
        for model in MODELS:
            path = D / f"sessions_{model}.jsonl"
            rows = jl(path)
            bad = [r for r in rows if r.get("error")]
            if not bad:
                continue
            part = D / f"sessions_{model}.partial.jsonl"  # survives a container restart
            prev = [r for r in jl(part) if r.get("case_id") and not r.get("error")]
            done = {(r["case_id"], r["attempt"]) for r in rows + prev if r.get("case_id") and not r.get("error")}
            env = Env()
            todo = [(c, at) for at in range(ATTEMPTS) for c in env.cases if (c, at) not in done]
            lock = threading.Lock()

            def one(j):
                r = session(url, env, j[0], model, j[1])
                if not r.get("error"):
                    with lock, part.open("a") as f:
                        f.write(json.dumps(r, ensure_ascii=False) + "\n")
                return r

            url, _ = deploy(f"dekr-{model}", MODELS[model])
            try:
                new = parallel(todo, one, n=16)
                with path.open("w") as f:
                    for r in [r for r in rows if not r.get("error")] + prev + new:
                        f.write(json.dumps(r, ensure_ascii=False) + "\n")
                print(f"{model}: reran {len(todo)}, {sum(1 for r in new if r.get('error'))} still failed", flush=True)
                if model == "dense":
                    judge(url)
            finally:
                stop(f"dekr-{model}")
        return
    url, _ = deploy("dekr-dense", MODELS["dense"])
    try:
        moe = {}

        def bring_up_moe():
            try:
                moe["url"], _ = deploy("dekr-moe", MODELS["moe"])
                run(moe["url"], "moe")
            finally:
                stop("dekr-moe")

        t = threading.Thread(target=bring_up_moe)
        t.start()
        run(url, "dense")
        t.join()
        judge(url)
    finally:
        stop("dekr-dense")
        stop("dekr-moe")


if __name__ == "__main__":
    main()
