"""One-page Swap Report: per candidate, the verdict, outcomes with intervals, endpoint findings, the three
worst conversations, the monthly cost difference and how many scenarios the verdict needed.

  python scripts/swap_report.py swapbench/reports/fintech.json --raw-root <dir> --out <dir> [--pdf]   (tau2 venv)

Config (JSON): {"domain", "title", "incumbent", "monthly_conversations", "margin",
  "runs": {"<run>": {"label", "raw": "<dir with split/results.json, relative to --raw-root>", "raw_splits": {...},
                     "serving": {"provider", "checkpoint", "quantization", "tool_parser", "reasoning", "hardware"},
                     "cost": {"per_conversation_usd": x, "basis": "..."}}}}
Outcome rows come from results/runs/<domain>/<run>.jsonl; transcripts (for the worst conversations and
the endpoint checks) from the raw tau2 results. The verdict uses every replayed scenario (visible + pool +
hidden: in a real swap there is no separate truth set) with the paired 95% CI gate of scripts/headline.py.
Writes <out>/index.html (the report), <out>/conversations/*.html and, with --pdf, <out>/swap-report.pdf.
"""
import argparse
import html
import json
import math
import os
import re
import subprocess
import sys
from collections import Counter
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from swapbench import stats, tau2_adapter  # noqa: E402

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RES = os.path.join(HERE, "results", "runs")
CHROME = os.environ.get("CHROME", "/opt/pw-browsers/chromium-1194/chrome-linux/chrome")
TOOL_TEXT = re.compile(r"<tool_call>|<function=|\"name\"\s*:\s*\"[a-z_]+\"\s*,\s*\"(arguments|parameters)\"")


def rows(dom, run):
    return [json.loads(x) for x in open(os.path.join(RES, dom, f"{run}.jsonl"))]


def mean_ci(eps, key, n_boot=4000, seed=0):
    import random
    per = list(stats.per_scenario(eps, key).values())
    rng = random.Random(seed)
    boots = sorted(sum(rng.choice(per) for _ in per) / len(per) for _ in range(n_boot))
    return sum(per) / len(per), boots[int(0.025 * n_boot)], boots[int(0.975 * n_boot) - 1]


def gate(q, h, m):
    if q["lo"] > -m and not (h["delta"] > 0.01 and h["lo"] > 0):
        return "SAFE"
    if q["hi"] < -m or (h["lo"] is not None and h["lo"] > 0.01):
        return "UNSAFE"
    return "NOT ENOUGH EVIDENCE"


def needed(cand, inc, m):
    """Scenarios a paired 95% CI needs to clear the margin at the observed effect (normal approximation)."""
    c, i = stats.per_scenario(cand, "reward"), stats.per_scenario(inc, "reward")
    d = [c[s] - i[s] for s in set(c) & set(i)]
    mu = sum(d) / len(d)
    sd = math.sqrt(sum((x - mu) ** 2 for x in d) / max(len(d) - 1, 1))
    ch, ih = stats.per_scenario(cand, "harmful_writes"), stats.per_scenario(inc, "harmful_writes")
    dh = [ch[s] - ih[s] for s in set(ch) & set(ih)]
    muh = sum(dh) / len(dh)
    sdh = math.sqrt(sum((x - muh) ** 2 for x in dh) / max(len(dh) - 1, 1))
    n_q = math.ceil((1.96 * sd / abs(mu + m)) ** 2) if abs(mu + m) > 1e-9 else None
    n_h = math.ceil((1.96 * sdh / (muh - 0.01)) ** 2) if muh > 0.01 else None
    return n_q, n_h


def raw_episodes(root, spec, dom):
    out = []
    for split in ("train", "pool", "test"):
        p = (spec.get("raw_splits") or {}).get(split) or os.path.join(spec["raw"], split, "results.json")
        p = os.path.join(root, p)
        if os.path.exists(p):
            for e in tau2_adapter.load(p, domain=dom):
                e["split"] = split
                out.append(e)
    return out


def endpoint_checks(eps):
    """Serving problems visible in transcripts: tool calls left as text, empty replies, abnormal endings, tool errors."""
    asst = [m for e in eps for m in e["messages"] if m["role"] == "assistant"]
    tools = [m for e in eps for m in e["messages"] if m["role"] == "tool"]
    text_calls = sum(1 for m in asst if not m.get("tool_calls") and TOOL_TEXT.search(m.get("content") or ""))
    empty = sum(1 for m in asst if not m.get("tool_calls") and not (m.get("content") or "").strip())
    term = Counter(e["termination"] for e in eps)
    abnormal = sum(v for k, v in term.items() if k not in ("user_stop", "agent_stop"))
    return {"turns": len(asst), "tool_call_as_text": text_calls, "empty_replies": empty,
            "abnormal_endings": abnormal, "abnormal_kinds": {k: v for k, v in term.items() if k not in ("user_stop", "agent_stop")},
            "tool_errors": sum(1 for m in tools if m.get("error")), "tool_results": len(tools),
            "infra_errors": sum(1 for e in eps if e["infra_error"]), "conversations": len(eps)}


def findings(spec, chk, inc_chk):
    out = []
    sv = spec.get("serving") or {}
    if sv.get("quantization") and sv["quantization"].lower() not in ("none", "bf16", "provider"):
        out.append(("info", f"{sv['quantization']}: compare with the full-precision checkpoint before blaming the model."))
    if sv.get("tool_parser") and "own format" not in sv["tool_parser"] and "qwen3_coder" not in sv["tool_parser"]:
        out.append(("info", f"Tool-call parser: {sv['tool_parser']}."))
    if sv.get("reasoning") and sv["reasoning"].startswith("off"):
        out.append(("info", f"Reasoning: {sv['reasoning']}."))
    rate = chk["tool_call_as_text"] / max(chk["turns"], 1)
    if rate > 0.01:
        out.append(("bad", f"{chk['tool_call_as_text']} of {chk['turns']} replies ({rate:.0%}) contain a tool call left as "
                           "text: the serving stack's tool parser does not match the model's format."))
    if chk["empty_replies"] / max(chk["turns"], 1) > 0.01:
        out.append(("bad", f"{chk['empty_replies']} empty replies ({chk['empty_replies'] / chk['turns']:.0%} of turns)."))
    ab, inc_ab = chk["abnormal_endings"] / chk["conversations"], inc_chk["abnormal_endings"] / inc_chk["conversations"]
    if ab > inc_ab + 0.02:
        kinds = ", ".join(f"{k} {v}" for k, v in chk["abnormal_kinds"].items())
        out.append(("bad", f"{chk['abnormal_endings']} conversations ({ab:.0%}) ended abnormally ({kinds}) vs {inc_ab:.0%} for the incumbent."))
    er, inc_er = chk["tool_errors"] / max(chk["tool_results"], 1), inc_chk["tool_errors"] / max(inc_chk["tool_results"], 1)
    if er > inc_er + 0.02:
        out.append(("bad", f"Tool errors on {er:.0%} of calls vs {inc_er:.0%} for the incumbent (malformed arguments)."))
    if chk["infra_errors"]:
        out.append(("bad", f"{chk['infra_errors']} conversations crashed (endpoint errors); counted as failures."))
    if not any(k == "bad" for k, _ in out):
        out.append(("ok", "No serving problems found in transcripts."))
    return out


def worst(cand_eps, inc_rows, k=3):
    """Failures on scenarios the incumbent always solved: harmful actions first, then any failure."""
    inc = stats.per_scenario(inc_rows, "reward")
    pool = [e for e in cand_eps if e["reward"] < 1 and inc.get(e["scenario"], 0) == 1]
    pool.sort(key=lambda e: (-e["harmful_writes"], e["split"] != "test", e["scenario"]))
    seen, out = set(), []
    for e in pool:
        if e["scenario"] not in seen:
            seen.add(e["scenario"])
            out.append(e)
        if len(out) == k:
            break
    return out


def what_went_wrong(e):
    """Extra and missing write actions against the scenario's correct resolution, in plain words."""
    from swapbench.tau2_adapter import WRITE_TOOLS, _canon_write
    writes = set().union(*WRITE_TOOLS.values())
    gold = [(a["name"], a.get("arguments") or {}) for a in (e["task"].get("evaluation_criteria") or {}).get("actions") or []
            if a["name"] in writes]
    errored = {m.get("id") for m in e["messages"] if m["role"] == "tool" and m.get("error")}
    done = [(t["name"], t.get("arguments") or {}) for m in e["messages"] if m["role"] == "assistant"
            for t in (m.get("tool_calls") or []) if t["name"] in writes and t.get("id") not in errored]
    key = lambda x: _canon_write(*x)  # noqa: E731
    gold_k, done_k = {key(x) for x in gold}, {key(x) for x in done}
    extra = [x for x in done if key(x) not in gold_k]
    missed = [x for x in gold if key(x) not in done_k]

    def words(n, args):
        w = n.replace("escalate_to_human", "transfer to human").replace("transfer_to_human_agents", "transfer to human").replace("_", " ")
        return f"{w} ({args['reason']})" if n == "escalate_to_human" and args.get("reason") else w
    wrong = sorted({n for n, _ in extra} & {n for n, _ in missed})
    parts = [f"wrong {words(n, {})} details" for n in wrong]
    ex = list(dict.fromkeys(words(n, a) for n, a in extra if n not in wrong))
    mi = list(dict.fromkeys(words(n, a) for n, a in missed if n not in wrong))
    parts += ([f"extra {', '.join(ex)}"] if ex else []) + ([f"missed {', '.join(mi)}"] if mi else [])
    return "; ".join(parts) or "wrong details"


def summarize(e):
    instr = e["task"]["user_scenario"]["instructions"]
    why = instr.get("reason_for_call") if isinstance(instr, dict) else str(instr)
    return re.sub(r"\s+", " ", why or "")[:140]


def conversation_page(e, run_label, inc_label, path):
    gold = [a for a in (e["task"].get("evaluation_criteria") or {}).get("actions") or []]
    msgs = []
    for m in e["messages"]:
        role = m["role"]
        if role == "assistant":
            body = html.escape(m.get("content") or "")
            for t in m.get("tool_calls") or []:
                body += f'<div class="call">→ {html.escape(t["name"])}({html.escape(json.dumps(t.get("arguments"), ensure_ascii=False))})</div>'
            msgs.append(f'<div class="m agent"><b>Agent ({html.escape(run_label)})</b>{body}</div>')
        elif role == "user":
            msgs.append(f'<div class="m cust"><b>Simulated customer</b>{html.escape(m.get("content") or "")}</div>')
        elif role == "tool":
            cls = "tool err" if m.get("error") else "tool"
            msgs.append(f'<div class="m {cls}"><b>Tool result</b><pre>{html.escape((m.get("content") or "")[:1500])}</pre></div>')
    gold_html = "".join(f"<li><code>{html.escape(a['name'])}({html.escape(json.dumps(a.get('arguments'), ensure_ascii=False))})</code></li>"
                        for a in gold)
    page = f"""<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(run_label)} · {html.escape(e['scenario'])}</title>
<style>{CSS_BASE}
.m{{padding:10px 12px;border-radius:8px;margin:8px 0;white-space:pre-wrap;overflow-wrap:anywhere}}
.m b{{display:block;font:600 .72rem/1.4 var(--mono);text-transform:uppercase;letter-spacing:.06em;color:var(--muted);margin-bottom:4px}}
.agent{{background:var(--paper);border:1px solid var(--rule)}}.cust{{background:var(--soft)}}
.tool{{background:var(--bg);border:1px dashed var(--rule);font-size:.85rem}}.err{{border-color:var(--bad)}}
.call{{font:.82rem/1.5 var(--mono);color:var(--accent);margin-top:4px}} pre{{margin:0;white-space:pre-wrap;font:.78rem/1.45 var(--mono)}}
</style><main>
<p><a href="../index.html">← Swap Report</a></p>
<h1>{html.escape(run_label)}: scenario {html.escape(e['scenario'])}</h1>
<p class="muted">{html.escape(summarize(e))}</p>
<p>Outcome: <b>{'passed' if e['reward'] >= 1 else 'failed'}</b> · harmful actions: <b>{e['harmful_writes']}</b> ·
the incumbent ({html.escape(inc_label)}) passed this scenario on every trial.</p>
<h2>Correct actions for this scenario</h2><ul>{gold_html}</ul>
<h2>Conversation</h2>{''.join(msgs)}</main>"""
    open(path, "w").write(page)


CSS_BASE = """
:root{--bg:#f3f5f4;--paper:#fff;--ink:#16211d;--muted:#5d6b65;--rule:#d5ddd9;--accent:#11665a;--soft:#e3efec;
--bad:#b0362a;--bad-soft:#f6e3df;--warn:#8a5a00;--warn-soft:#f6ecd6;--ok:#2d6e3e;--ok-soft:#e2f0e5;
--sans:"IBM Plex Sans",-apple-system,"Segoe UI",Roboto,Arial,sans-serif;--mono:"IBM Plex Mono",ui-monospace,Menlo,monospace}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--bg:#0e1513;--paper:#151e1b;--ink:#e3ebe7;--muted:#97a7a0;
--rule:#2a3733;--accent:#5cc2b2;--soft:#163029;--bad:#ef8a7c;--bad-soft:#3a201c;--warn:#e2b25c;--warn-soft:#33290f;--ok:#7ccf91;--ok-soft:#173022;color-scheme:dark}}
:root[data-theme="dark"]{--bg:#0e1513;--paper:#151e1b;--ink:#e3ebe7;--muted:#97a7a0;--rule:#2a3733;--accent:#5cc2b2;--soft:#163029;
--bad:#ef8a7c;--bad-soft:#3a201c;--warn:#e2b25c;--warn-soft:#33290f;--ok:#7ccf91;--ok-soft:#173022;color-scheme:dark}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:400 14px/1.5 var(--sans);
padding-left:max(16px,env(safe-area-inset-left,0px));padding-right:max(16px,env(safe-area-inset-right,0px));padding-block:24px 40px}
main{max-width:1180px;margin:0 auto}h1{font-size:1.45rem;line-height:1.2;margin:0 0 6px;text-wrap:balance}
h2{font-size:1rem;margin:20px 0 8px}a{color:var(--accent)}.muted{color:var(--muted)}code{font:.82rem var(--mono)}
"""


def render(cfg, cands, inc_label, meta, out_dir):
    def pct(t):
        return f"{t[0]*100:.1f}%<span class=ci>[{t[1]*100:.1f}, {t[2]*100:.1f}]</span>"

    def harm(t):
        return f"{t[0]:.3f}<span class=ci>[{t[1]:.3f}, {t[2]:.3f}]</span>"

    def money(x):
        s = "−" if x < 0 else "+"
        return f"{s}${abs(x):,.0f}"
    trs = []
    for c in cands:
        v = c["verdict"]
        vcls = {"SAFE": "v-safe", "UNSAFE": "v-unsafe"}.get(v, "v-nee")
        f_html = "".join(f'<li class="f-{k}">{html.escape(t)}</li>' for k, t in c["findings"])
        w_html = "".join(f'<li><a href="conversations/{w["file"]}">{html.escape(w["scenario"])}</a> '
                         f'<span class=muted>{html.escape(w["why"])}</span></li>' for w in c["worst"]) or "<li class=muted>none</li>"
        opts = [(n, k) for n, k in zip(c["needed"], ("success", "harm")) if n]
        n_min, which = min(opts) if opts else (None, "")
        need = f"{n_min:,} ({which})" if n_min else "n/a"
        need_h = ""
        trs.append(f"""<tr>
<td><div class=name>{html.escape(c['label'])}</div><div class="muted small">{html.escape(c['serving_line'])}</div></td>
<td><span class="verdict {vcls}">{v}</span></td>
<td class=num>{pct(c['success'])}<div class="small {'neg' if c['delta']['delta'] < 0 else ''}">{c['delta']['delta']*100:+.1f} pts
<span class=ci>[{c['delta']['lo']*100:+.1f}, {c['delta']['hi']*100:+.1f}]</span></div></td>
<td class=num>{harm(c['harm'])}<div class=small>{c['harm_delta']['delta']:+.3f}<span class=ci>[{c['harm_delta']['lo']:+.3f}, {c['harm_delta']['hi']:+.3f}]</span></div></td>
<td class=num>{money(c['monthly_delta'])}<div class="small muted">{c['cost_pc']*100:.2f}¢ / conv.</div></td>
<td class=num>{c['n_scen']}<div class="small muted wl">needed {need}{need_h}</div></td>
<td><ul class=f>{f_html}</ul></td>
<td><ul class=w>{w_html}</ul></td></tr>""")
    page = f"""<meta charset="utf-8"><title>{html.escape(cfg['title'])}</title>
<meta name="claude:viewport-fit-sides" content="cover">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;600&family=IBM+Plex+Sans:wght@400;600;700&display=swap">
<style>{CSS_BASE}
header{{display:flex;flex-wrap:wrap;justify-content:space-between;gap:12px 32px;align-items:flex-end;margin-bottom:14px}}
.eyebrow{{font:600 .7rem/1 var(--mono);letter-spacing:.1em;text-transform:uppercase;color:var(--accent)}}
.meta{{display:grid;grid-template-columns:repeat(4,auto);gap:4px 18px;font-size:.8rem}}.meta span{{color:var(--muted)}}
.wrap{{overflow-x:auto;background:var(--paper);border:1px solid var(--rule);border-radius:10px}}
table{{border-collapse:collapse;width:100%;min-width:1080px;table-layout:fixed}}
col.c1{{width:13%}}col.c2{{width:10%}}col.c3{{width:13%}}col.c4{{width:13%}}col.c5{{width:9%}}col.c6{{width:9%}}col.c7{{width:16%}}col.c8{{width:17%}}th,td{{text-align:left;vertical-align:top;padding:9px 10px;border-bottom:1px solid var(--rule)}}
th{{font:600 .66rem/1.25 var(--mono);text-transform:uppercase;letter-spacing:.06em;color:var(--muted);background:var(--bg)}}
tr:last-child td{{border-bottom:0}}.name{{font-weight:600}}.small{{font-size:.76rem}}.num{{font-family:var(--mono);font-variant-numeric:tabular-nums}}
.ci{{color:var(--muted);font-size:.72rem;margin-left:4px}}.neg{{color:var(--bad)}}
.verdict{{display:inline-block;font:600 .66rem/1.25 var(--mono);letter-spacing:.04em;padding:4px 6px;border-radius:4px;max-width:100%}}
.wl{{white-space:normal}}
.v-safe{{background:var(--ok-soft);color:var(--ok)}}.v-unsafe{{background:var(--bad-soft);color:var(--bad)}}.v-nee{{background:var(--warn-soft);color:var(--warn)}}
ul.f,ul.w{{margin:0;padding-left:14px;font-size:.74rem;line-height:1.35;display:flex;flex-direction:column;gap:2px}}
.num .ci{{display:block;margin-left:0}}
.f-bad{{color:var(--bad)}}.f-ok{{color:var(--ok)}}.f-info{{color:var(--muted)}}
.notes{{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px 24px;font-size:.78rem;color:var(--muted);margin-top:14px}}
.notes b{{color:var(--ink)}}@media(max-width:760px){{.notes{{grid-template-columns:1fr}}.meta{{grid-template-columns:repeat(2,auto)}}}}
@page{{size:A3 landscape;margin:8mm}}
@media print{{html{{zoom:.93}}body{{padding:0;background:#fff}}main{{max-width:none}}table{{min-width:0}}th,td{{padding:5px 6px}}
.notes{{font-size:.7rem;margin-top:8px}}h1{{font-size:1.2rem}}}}
</style>
<main>
<header><div><div class=eyebrow>Swap Report · {html.escape(cfg['domain'])}</div><h1>{html.escape(cfg['title'])}</h1>
<div class=muted>Can each candidate replace <b>{html.escape(inc_label.replace(" (incumbent)", ""))}</b> without hurting customers? Verdicts from full replays of
simulated customer conversations against a stateful copy of the tools, graded by end state.</div></div>
<div class=meta><span>Incumbent</span><b>{html.escape(inc_label.replace(" (incumbent)", ""))}</b><span>Scenarios</span><b>{meta['scenarios']}</b>
<span>Conversations</span><b>{meta['conversations']:,}</b><span>Simulated turns</span><b>{meta['sim_share']:.0%}</b>
<span>Volume</span><b>{cfg['monthly_conversations']:,}/mo</b><span>Margin</span><b>{cfg['margin']:.0f} pts</b>
<span>Incumbent success</span><b>{meta['inc_success']*100:.1f}%</b><span>Date</span><b>{meta['date']}</b></div></header>
<div class=wrap><table><colgroup><col class=c1><col class=c2><col class=c3><col class=c4><col class=c5><col class=c6><col class=c7><col class=c8></colgroup><thead><tr><th>Candidate</th><th>Verdict</th><th>Task success [95% CI]<br>Δ vs incumbent</th>
<th>Harmful actions / conv.<br>Δ vs incumbent</th><th>Monthly cost Δ</th><th>Scenarios used<br>(needed)</th>
<th>Endpoint findings</th><th>Three worst conversations</th></tr></thead><tbody>{''.join(trs)}</tbody></table></div>
<div class=notes>
<div><b>Verdict.</b> SAFE: the 95% CI of the success difference stays above −{cfg['margin']:.0f} points and harmful actions don't rise.
UNSAFE: the CI is entirely below −{cfg['margin']:.0f} points, or harmful actions rise (lower bound &gt; 0.01 per conversation).
Otherwise NOT ENOUGH EVIDENCE, with the number of scenarios a verdict would need at the observed effect.</div>
<div><b>Harmful action.</b> A successful write (refund, dispute, freeze, transfer, order change) that the scenario's correct
resolution does not contain. <b>Simulated turns</b>: share of all conversation turns spoken by the simulated customer
({html.escape(meta['user_model'])}); every tool call ran against the stateful copy of the tools.</div>
<div><b>Cost.</b> {html.escape(meta['cost_note'])} Monthly difference at {cfg['monthly_conversations']:,} conversations.
<b>Worst conversations</b>: failures on scenarios the incumbent solved on every trial, harmful ones first.</div>
</div></main>"""
    open(os.path.join(out_dir, "index.html"), "w").write(page)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("config")
    ap.add_argument("--raw-root", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--pdf", action="store_true")
    a = ap.parse_args()
    cfg = json.load(open(a.config))
    dom, m = cfg["domain"], cfg["margin"] / 100
    os.makedirs(os.path.join(a.out, "conversations"), exist_ok=True)
    inc_name = cfg["incumbent"]
    inc_spec = cfg["runs"][inc_name]
    inc_rows = rows(dom, inc_name)
    inc_eps = raw_episodes(a.raw_root, inc_spec, dom)
    inc_chk = endpoint_checks(inc_eps)
    cands, sim_turns, all_turns, convs, scen = [], 0, 0, 0, set()
    for r in inc_rows:
        sim_turns, all_turns = sim_turns + r["customer_turns"], all_turns + r["customer_turns"] + r["agent_turns"]
    convs += len(inc_rows)
    for run, spec in cfg["runs"].items():
        if run == inc_name:
            continue
        cr = rows(dom, run)
        convs += len(cr)
        scen |= {r["scenario"] for r in cr}
        for r in cr:
            sim_turns, all_turns = sim_turns + r["customer_turns"], all_turns + r["customer_turns"] + r["agent_turns"]
        q, h = stats.paired_delta(cr, inc_rows), stats.paired_delta(cr, inc_rows, "harmful_writes")
        eps = raw_episodes(a.raw_root, spec, dom)
        chk = endpoint_checks(eps)
        ws = []
        for e in worst(eps, inc_rows):
            fn = f"{run}_{e['scenario']}_{e['trial']}.html".replace("/", "_")
            conversation_page(e, spec["label"], inc_spec["label"], os.path.join(a.out, "conversations", fn))
            ws.append({"file": fn, "scenario": e["scenario"], "why": what_went_wrong(e), "harm": e["harmful_writes"]})
        cost_pc = spec["cost"]["per_conversation_usd"]
        sv = spec.get("serving") or {}
        cands.append({
            "label": spec["label"], "verdict": gate(q, h, m), "success": mean_ci(cr, "reward"), "harm": mean_ci(cr, "harmful_writes"),
            "delta": q, "harm_delta": h, "n_scen": q["n"], "needed": needed(cr, inc_rows, m),
            "cost_pc": cost_pc, "monthly_delta": (cost_pc - inc_spec["cost"]["per_conversation_usd"]) * cfg["monthly_conversations"],
            "findings": findings(spec, chk, inc_chk), "worst": ws,
            "serving_line": " · ".join(x for x in (sv.get("provider"), sv.get("checkpoint"), sv.get("hardware")) if x)})
    meta = {"scenarios": len(scen | {r["scenario"] for r in inc_rows}), "conversations": convs, "sim_share": sim_turns / all_turns,
            "inc_success": stats.mean(inc_rows, "reward"), "date": cfg.get("date") or date.today().isoformat(),
            "user_model": cfg.get("user_model", "simulated customer"), "cost_note": cfg.get("cost_note", "")}
    render(cfg, cands, inc_spec["label"], meta, a.out)
    json.dump({"meta": meta, "candidates": [{k: v for k, v in c.items()} for c in cands]},
              open(os.path.join(a.out, "report.json"), "w"), indent=1, default=str)
    if a.pdf:
        subprocess.run([CHROME, "--headless", "--no-sandbox", "--disable-gpu", "--no-pdf-header-footer",
                        f"--print-to-pdf={os.path.abspath(os.path.join(a.out, 'swap-report.pdf'))}",
                        "file://" + os.path.abspath(os.path.join(a.out, "index.html"))], capture_output=True, timeout=120)
    print("wrote", a.out)


if __name__ == "__main__":
    main()
