"""Build results.csv, the analysis tables (tables.md) and the cost-vs-success charts (charts/*.svg).

  python harness/report.py

Rules: last record per task; tasks that ended in an API error are excluded (provider trouble, re-runnable); every
other failure counts as unresolved. Pooled numbers use only models that have all ten use cases, weight every use case
equally (100 tasks each) and resample within use case. Intervals are bootstrap 95%, paired on the same tasks.
"""
import csv
import glob
import json
import math
import os
import random
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from harness import models as M  # noqa: E402

INFRA = ("api_error", "account_blocked", "timeout")
UCS_ALL = ["support", "invoice_extraction", "claims_triage", "kyc_checks", "contract_review", "sql_analyst",
           "lead_qualification", "it_access", "pr_review", "meeting_to_crm"]
# Use cases with result files. With all ten present this is UCS_ALL, as in the original run; without the support rows
# (the private SwapBench split is not in the public repo) the pooled tables cover the nine harness use cases.
UCS = [u for u in UCS_ALL if glob.glob(os.path.join(ROOT, "results", u, "*.jsonl"))] or UCS_ALL
_UNUSED = ["support", "invoice_extraction", "claims_triage", "kyc_checks", "contract_review", "sql_analyst",
       "lead_qualification", "it_access", "pr_review", "meeting_to_crm"]
NAMES = {"support": "Support tickets", "invoice_extraction": "Invoice extraction", "claims_triage": "Claims triage",
         "kyc_checks": "KYC checks", "contract_review": "Contract review", "sql_analyst": "SQL analyst",
         "lead_qualification": "Lead qualification", "it_access": "IT access requests", "pr_review": "PR review",
         "meeting_to_crm": "Meeting notes to CRM"}


FULL = "--full" in sys.argv
EXCL = {} if FULL or not os.path.exists(os.path.join(ROOT, "audit_exclusions.json")) else \
    json.load(open(os.path.join(ROOT, "audit_exclusions.json")))


PAIRED_OUT = []  # claims_triage re-run on the fixed generator (Oct 20)


def load_all():
    data = {}
    for p in glob.glob(os.path.join(ROOT, "results", "*", "*.jsonl")):
        uc = os.path.basename(os.path.dirname(p))
        model, arm = os.path.basename(p)[:-6].split("__")
        rows = {}
        for l in open(p):
            r = json.loads(l)
            rows[r["task"]] = r
        if not FULL and uc in PAIRED_OUT:
            uc = uc + "*"  # kept for the unpaired side table only
        data[(uc, model, arm)] = {t: r for t, r in rows.items()
                                  if r["status"] not in INFRA and t not in EXCL.get(uc.rstrip("*"), {})}
        data[(uc, model, arm, "infra")] = sum(r["status"] in INFRA for r in rows.values())
    return data


def stats(rows):
    rs = list(rows.values())
    n = len(rs)
    s = sum(r["success"] for r in rs)
    c = sum(r["cost"] for r in rs)
    lat = sorted(r["latency"] for r in rs)
    fails = {}
    for r in rs:
        for f in set(r["failures"]):
            fails[f] = fails.get(f, 0) + 1
    return dict(n=n, success=s / n if n else float("nan"), rule_break=sum(bool(r["rule_breaks"]) for r in rs) / n if n else 0,
                cost_per_task=c / n if n else 0, cost_per_success=c / s if s else float("inf"),
                p50=lat[n // 2] if n else 0, p95=lat[min(int(0.95 * n), n - 1)] if n else 0, failures=fails,
                jev_cost=sum(r.get("jev_cost", 0) for r in rs) / n if n else 0)


def pooled(data, model, arm="none", ucs=UCS):
    out = {}
    for uc in ucs:
        for t, r in data.get((uc, model, arm), {}).items():
            out[(uc, t)] = r
    return out


def has_all(data, model, arm="none", ucs=UCS):
    return all(len(data.get((uc, model, arm), {})) >= 50 for uc in ucs)


def boot(a, b, n_boot=3000, seed=1):
    """Paired success difference a-b (pts) and cost-per-success ratio a/b, stratified by use case."""
    keys = sorted(set(a) & set(b))
    groups = {}
    for k in keys:
        groups.setdefault(k[0], []).append(k)
    rng = random.Random(seed)

    def st(ks):
        sa = sum(a[k]["success"] for k in ks)
        sb = sum(b[k]["success"] for k in ks)
        ca = sum(a[k]["cost"] for k in ks)
        cb = sum(b[k]["cost"] for k in ks)
        return (sa - sb) / len(ks) * 100, ((ca / sa) / (cb / sb)) if sa and sb else float("nan")

    d0, r0 = st(keys)
    ds, rs = [], []
    for _ in range(n_boot):
        ks = [k for g in groups.values() for k in (rng.choice(g) for _ in g)]
        d, r = st(ks)
        ds.append(d)
        rs.append(r)
    ds.sort()
    rs.sort()
    i, j = int(0.025 * n_boot), int(0.975 * n_boot) - 1
    return dict(n=len(keys), d=d0, lo=ds[i], hi=ds[j], r=r0, rlo=rs[i], rhi=rs[j])


def fmt_ci(b):
    call = "not enough evidence" if b["lo"] <= 0 <= b["hi"] else ""
    return f"{b['d']:+.1f} [{b['lo']:+.1f}, {b['hi']:+.1f}]" + (f" ({call})" if call else "")


def label(model):
    return model.replace("@", " @ ")


def svg_chart(points, title, path):
    """points: [(label, cost_per_success_usd, success_frac, kind)]; log-x cost per success, y success."""
    W, H, L, R, T, B = 820, 520, 64, 24, 84, 50
    pts = [p for p in points if p[1] and math.isfinite(p[1]) and p[1] > 0]
    if not pts:
        return
    xs = [math.log10(p[1] * 100) for p in pts]  # cents
    lo, hi = min(xs) - 0.12, max(xs) + 0.35
    ymin = max(0.0, math.floor(min(p[2] for p in pts) * 10) / 10 - 0.05)
    X = lambda v: L + (math.log10(v * 100) - lo) / (hi - lo) * (W - L - R)  # noqa: E731
    Y = lambda s: T + (1 - (s - ymin) / (1 - ymin)) * (H - T - B)  # noqa: E731
    color = {"closed": "var(--closed)", "open": "var(--open)", "jev": "var(--jev)"}
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" font-family="system-ui,sans-serif" font-size="11">',
           "<style>:root{--fg:#1f2328;--muted:#6e7781;--grid:#e3e7eb;--closed:#c2410c;--open:#1d4ed8;--jev:#047857;--bg:#ffffff}"
           "@media (prefers-color-scheme: dark){:root{--fg:#e6edf3;--muted:#9aa4ae;--grid:#30363d;--closed:#fb923c;--open:#60a5fa;--jev:#34d399;--bg:#0d1117}}"
           "text{fill:var(--fg)} .m{fill:var(--muted)}</style>",
           f'<rect width="{W}" height="{H}" fill="var(--bg)"/>',
           f'<text x="{L}" y="22" font-size="14" font-weight="600">{title}</text>']
    lx = L
    for k, t in (("closed", "closed model"), ("open", "open model"), ("jev", "with Jev check")):
        if any(p[3] == k for p in pts):
            out.append(f'<circle cx="{lx + 5}" cy="40" r="5" fill="{color[k]}"/><text class="m" x="{lx + 14}" y="44">{t}</text>')
            lx += 120
    out.append(f'<text class="m" x="{lx + 10}" y="44">dashed line: cheapest model at each success level (frontier)</text>')
    k0 = int(math.ceil(ymin * 10))
    for k in range(k0, 11):
        y = Y(k / 10)
        out.append(f'<line x1="{L}" x2="{W - R}" y1="{y:.1f}" y2="{y:.1f}" stroke="var(--grid)"/>'
                   f'<text class="m" x="{L - 8}" y="{y + 4:.1f}" text-anchor="end">{k * 10}%</text>')
    for e in range(math.ceil(lo), math.floor(hi) + 1):
        for mult in (1, 3):
            v = mult * 10 ** e
            lv = math.log10(v)
            if not lo <= lv <= hi:
                continue
            x = L + (lv - lo) / (hi - lo) * (W - L - R)
            lab = f"{v:g}¢" if v < 100 else f"${v / 100:g}"
            out.append(f'<line x1="{x:.1f}" x2="{x:.1f}" y1="{T}" y2="{H - B}" stroke="var(--grid)"/>'
                       f'<text class="m" x="{x:.1f}" y="{H - B + 16}" text-anchor="middle">{lab}</text>')
    out.append(f'<text class="m" x="{(L + W - R) / 2}" y="{H - 12}" text-anchor="middle">cost per successful task (log scale)</text>')
    out.append(f'<text class="m" transform="translate(16,{(T + H - B) / 2}) rotate(-90)" text-anchor="middle">success rate</text>')
    front = []
    for p in sorted(pts, key=lambda p: p[1]):
        if not front or p[2] > front[-1][2]:
            front.append(p)
    if len(front) > 1:
        out.append('<polyline fill="none" stroke="var(--muted)" stroke-dasharray="4 3" points="' +
                   " ".join(f"{X(p[1]):.1f},{Y(p[2]):.1f}" for p in front) + '"/>')
    boxes = [(X(p[1]) - 6, Y(p[2]) - 6, X(p[1]) + 6, Y(p[2]) + 6) for p in pts]
    marks, labels, keyed = [], [], []
    for p in sorted(pts, key=lambda p: -p[2]):
        x, y = X(p[1]), Y(p[2])
        w = 6.2 * len(p[0])
        chosen = None
        for dx, dy, anchor in ((9, 4, "start"), (9, -7, "start"), (9, 15, "start"), (-9, 4, "end"), (-9, -7, "end"),
                               (-9, 15, "end"), (9, -18, "start"), (9, 26, "start"), (-9, -18, "end"), (-9, 26, "end")):
            x0 = x + dx if anchor == "start" else x + dx - w
            bx = (x0, y + dy - 10, x0 + w, y + dy + 2)
            if bx[2] > W - 4 or bx[0] < L + 2:
                continue
            if not any(bx[0] < b[2] and bx[2] > b[0] and bx[1] < b[3] and bx[3] > b[1] for b in boxes):
                chosen = (dx, dy, anchor, bx)
                break
        marks.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="5" fill="{color[p[3]]}" stroke="var(--bg)" stroke-width="1.5"/>')
        if chosen:
            dx, dy, anchor, bx = chosen
            boxes.append(bx)
            if abs(dy) > 10:
                tx = x + dx
                labels.append(f'<line x1="{x:.1f}" y1="{y:.1f}" x2="{tx:.1f}" y2="{y + dy - 4:.1f}" stroke="var(--muted)" stroke-width="0.6"/>')
            labels.append(f'<text x="{x + dx:.1f}" y="{y + dy:.1f}" text-anchor="{anchor}">{p[0]}</text>')
        else:  # no room for the name: number the point and list it under the chart
            keyed.append(p[0])
            labels.append(f'<text x="{x + 7:.1f}" y="{y - 5:.1f}" font-size="10" font-weight="600">{len(keyed)}</text>')
    out += marks + labels
    if keyed:
        rows = [f"{i + 1} {n}" for i, n in enumerate(keyed)]
        H2 = H + 16 * ((len(rows) + 2) // 3) + 10
        out[0] = out[0].replace(f'viewBox="0 0 {W} {H}"', f'viewBox="0 0 {W} {H2}"')
        out[2] = f'<rect width="{W}" height="{H2}" fill="var(--bg)"/>'
        for i, row in enumerate(rows):
            out.append(f'<text class="m" x="{L + (i % 3) * 250}" y="{H + 8 + 16 * (i // 3)}">{row}</text>')
    out.append("</svg>")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    open(path, "w").write("\n".join(out))


def main():
    data = load_all()
    models = sorted({k[1] for k in data if len(k) == 3})
    arms = sorted({(k[1], k[2]) for k in data if len(k) == 3})
    # ---- results.csv ----
    rows = []
    for (uc, model, arm) in sorted(k for k in data if len(k) == 3):
        s = stats(data[(uc, model, arm)])
        api, ep, mid = M.endpoint(model)
        prov = "anthropic" if api == "anthropic" else ("openai" if ep == M.OPENAI else model.split("@")[1])
        rows.append(dict(use_case=uc, model=model.split("@")[0], provider=prov, arm=arm, tasks=s["n"],
                         api_errors_excluded=data[(uc, model, arm, "infra")], success=round(s["success"], 4),
                         hidden_rule_break_rate=round(s["rule_break"], 4), cost_per_task_usd=round(s["cost_per_task"], 6),
                         cost_per_success_usd=round(s["cost_per_success"], 6), latency_p50_s=round(s["p50"], 1),
                         latency_p95_s=round(s["p95"], 1), failures=json.dumps(s["failures"]),
                         price_in_cached_out=str(M.MODELS[model][3])))
    with open(os.path.join(ROOT, "results_full_set.csv" if FULL else "results.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)

    md = ["# Haiku Tax: generated tables" + (" (full task set, before the audit)" if FULL else " (audited task set)"), "",
          "Synthetic tasks, simulated environments. One run per task, 100 tasks per use case"
          + ("" if FULL else ", minus the tasks the grader audit excluded (audit_exclusions.json: gold or grader "
                             "errors and hidden rules the written policy contradicts)")
          + ". Pooled numbers pool tasks over the ten use cases. Paired bootstrap 95% intervals over the same tasks, "
          "resampled within use case. Generated by `harness/report.py`; do not edit by hand.", ""]
    full = [m for m in models if has_all(data, m)]
    P = {m: pooled(data, m) for m in full}
    S = {m: stats(P[m]) for m in full}
    closed = [m for m in full if M.MODELS[m][4].startswith("closed")]
    opn = [m for m in full if M.MODELS[m][4] == "open"]

    md += ["## Overall (all ten use cases)", "",
           "| model | provider | success | hidden-rule break rate | cost per task | cost per success | p50 / p95 latency | empty replies | tool-call parse errors |",
           "|---|---|---|---|---|---|---|---|---|"]
    for m in sorted(full, key=lambda m: S[m]["cost_per_success"]):
        s = S[m]
        md.append(f"| {m.split('@')[0]} | {m.split('@')[1] if '@' in m else ('anthropic' if 'opus' in m or 'sonnet' in m or 'haiku' in m else 'openai')} "
                  f"| {s['success']:.1%} | {s['rule_break']:.1%} | {s['cost_per_task'] * 100:.2f}¢ | {s['cost_per_success'] * 100:.2f}¢ "
                  f"| {s['p50']:.0f}s / {s['p95']:.0f}s | {s['failures'].get('empty_reply', 0)} | {s['failures'].get('tool_parse_error', 0)} |")
    md.append("")

    md += ["## Price-matched pairs", "",
           "For each closed tier: the open model/provider with the highest pooled success whose cost per successful task is "
           "equal or lower, and the paired difference (open minus closed). Also the best open model at any price.", "",
           "| closed model | its success / cost per success | best open at <= its cost per success | success difference [95% CI] | cost per success ratio open/closed [95% CI] | best open at any price | difference [95% CI] |",
           "|---|---|---|---|---|---|---|"]
    for c in sorted(closed, key=lambda m: S[m]["cost_per_success"]):
        cand = [o for o in opn if S[o]["cost_per_success"] <= S[c]["cost_per_success"]]
        # Ties on success go to the lower cost per success. The original run broke ties by model-key order, which with
        # the original provider names gave the same choice; with the neutral provider labels the key order flips.
        best = max(cand, key=lambda o: (S[o]["success"], -S[o]["cost_per_success"])) if cand else None
        best_any = max(opn, key=lambda o: (S[o]["success"], -S[o]["cost_per_success"])) if opn else None
        b1 = boot(P[best], P[c]) if best else None
        b2 = boot(P[best_any], P[c]) if best_any else None
        md.append(f"| {c} | {S[c]['success']:.1%} / {S[c]['cost_per_success'] * 100:.2f}¢ | "
                  + (f"{label(best)} ({S[best]['success']:.1%}, {S[best]['cost_per_success'] * 100:.2f}¢) | {fmt_ci(b1)} | "
                     f"{b1['r']:.2f} [{b1['rlo']:.2f}, {b1['rhi']:.2f}]" if best else "none | — | —")
                  + (f" | {label(best_any)} ({S[best_any]['success']:.1%}) | {fmt_ci(b2)} |" if best_any else " | — | — |"))
    md.append("")

    md += ["## Every open model vs every closed model (pooled success difference, open minus closed)", "",
           "| open \\ closed | " + " | ".join(closed) + " |", "|---|" + "---|" * len(closed)]
    for o in sorted(opn, key=lambda m: -S[m]["success"]):
        md.append(f"| {label(o)} ({S[o]['success']:.0%}) | " + " | ".join(fmt_ci(boot(P[o], P[c])) for c in closed) + " |")
    md.append("")

    md += ["## Per use case: success (cost per success)", "",
           "| model | " + " | ".join(NAMES[u] for u in UCS) + " |", "|---|" + "---|" * len(UCS)]
    for m in sorted(full, key=lambda m: -S[m]["success"]):
        cells = []
        for u in UCS:
            s = stats(data.get((u, m, "none"), {}))
            cells.append(f"{s['success']:.0%} ({s['cost_per_success'] * 100:.2f}¢)" if s["n"] else "—")
        md.append(f"| {label(m)} | " + " | ".join(cells) + " |")
    md.append("")

    trig = {}
    for u in UCS:
        if u == "support":
            continue
        import importlib
        for t in importlib.import_module("envs." + u).ENV.tasks():
            trig[(u, t["id"])] = bool(t.get("triggers"))
    md += ["## Where the gap is: tasks with and without a hidden rule (nine harness use cases)", "",
           "Hidden rules are prudence rules the agent is never told (see each environment's README). On tasks where no hidden "
           "rule applies, the written policy alone determines the right action.", "",
           "| model | success, no hidden rule | success, hidden-rule tasks | hidden-rule break rate on hidden-rule tasks |",
           "|---|---|---|---|"]
    split = []
    for m in full:
        a = [r for (u, t), r in P[m].items() if (u, t) in trig and not trig[(u, t)]]
        b = [r for (u, t), r in P[m].items() if (u, t) in trig and trig[(u, t)]]
        if a and b:
            split.append((m, sum(r["success"] for r in a) / len(a), sum(r["success"] for r in b) / len(b),
                          sum(bool(r["rule_breaks"]) for r in b) / len(b), len(a), len(b)))
    for m, x, y, z, na, nb in sorted(split, key=lambda r: -r[1]):
        md.append(f"| {label(m)} | {x:.1%} (n={na}) | {y:.1%} (n={nb}) | {z:.1%} |")
    md.append("")

    md += ["## Models run on part of the grid", "",
           "An inference provider blocked our account on Oct 20 before these finished. Each is compared with Haiku 5.5 "
           "and DeepSeek V4.1 Flash (provider-b) on the use cases it completed, paired on the same tasks.", "",
           "| model | use cases done | success | vs Haiku 5.5 [95% CI] | vs DeepSeek V4.1 Flash @ provider-b [95% CI] | cost per success | Haiku cost per success on the same tasks |",
           "|---|---|---|---|---|---|---|"]
    for m in models:
        if m in full or not M.MODELS.get(m) or M.MODELS[m][4] != "open":
            continue
        ucs = [u for u in UCS if len(data.get((u, m, "none"), {})) >= 50]
        if not ucs:
            continue
        pm, ph, pd = pooled(data, m, ucs=ucs), pooled(data, "haiku-5.5", ucs=ucs), pooled(data, "deepseek-v4.1-flash@provider-b", ucs=ucs)
        sm = stats(pm)
        bh, bd = boot(pm, ph), boot(pm, pd)
        keys = set(pm) & set(ph)
        hs = stats({k: ph[k] for k in keys})
        md.append(f"| {label(m)} | {len(ucs)} | {sm['success']:.1%} | {fmt_ci(bh)} | {fmt_ci(bd)} | {sm['cost_per_success'] * 100:.2f}¢ | {hs['cost_per_success'] * 100:.2f}¢ |")
    md.append("")

    md += ["## Provider spread (same model, provider-a vs provider-b)", "",
           "| model | provider-a success / cost per success / empty replies | provider-b success / cost per success / empty replies | provider-a minus provider-b [95% CI] |",
           "|---|---|---|---|"]
    for base in sorted({m.split("@")[0] for m in models if "@" in m}):
        a, b = f"{base}@provider-a", f"{base}@provider-b"
        if a in models and b in models:
            ucs = [u for u in UCS if len(data.get((u, a, "none"), {})) >= 50 and len(data.get((u, b, "none"), {})) >= 50]
            pa, pb = pooled(data, a, ucs=ucs), pooled(data, b, ucs=ucs)
            sa, sb = stats(pa), stats(pb)
            bb = boot(pa, pb)
            md.append(f"| {base} ({len(ucs)} use cases) | {sa['success']:.1%} / {sa['cost_per_success'] * 100:.2f}¢ / {sa['failures'].get('empty_reply', 0)} "
                      f"| {sb['success']:.1%} / {sb['cost_per_success'] * 100:.2f}¢ / {sb['failures'].get('empty_reply', 0)} | {fmt_ci(bb)} |")
    md.append("")

    md += ["## Effect of the Jev check (criteria from the written policy only)", "",
           "Six use cases with state-changing actions. Paired, check minus no check. v1: last 12 lookups cut to 1,500 "
           "characters each, block at p > 0.5. Final (v3): every lookup in full, neutral criteria, block at p > 0.8; "
           "chosen on a held-out development sample (tasks 101-120 by id hash), evaluated here on the 100 test tasks.", "",
           "| model | version | success without / with | success difference [95% CI] | hidden-rule break rate without / with | break difference [95% CI] | cost per task without / with (of which Jev) | actions blocked |",
           "|---|---|---|---|---|---|---|---|"]
    for (m, arm) in sorted(arms, key=lambda x: (x[0], x[1])):
        if arm not in ("jev", "jev3"):
            continue
        ucs = [u for u in UCS if data.get((u, m, arm))]
        pj, pn = pooled(data, m, arm, ucs), pooled(data, m, "none", ucs)
        keys = set(pj) & set(pn)
        pj = {k: pj[k] for k in keys}
        pn = {k: pn[k] for k in keys}
        if not keys:
            continue
        sj, sn = stats(pj), stats(pn)
        bs = boot(pj, pn)
        brk_j = {k: dict(v, success=bool(v["rule_breaks"]), cost=v["cost"]) for k, v in pj.items()}
        brk_n = {k: dict(v, success=bool(v["rule_breaks"]), cost=v["cost"]) for k, v in pn.items()}
        bb = boot(brk_j, brk_n)
        nchk = sum(len(r.get("checks", [])) for r in pj.values())
        nblk = sum(c.get("blocked", False) for r in pj.values() for c in r.get("checks", []))
        md.append(f"| {label(m)} | {'v1' if arm == 'jev' else 'final (v3)'} | {sn['success']:.1%} / {sj['success']:.1%} | {fmt_ci(bs)} | {sn['rule_break']:.1%} / {sj['rule_break']:.1%} "
                  f"| {fmt_ci(bb)} | {sn['cost_per_task'] * 100:.3f}¢ / {sj['cost_per_task'] * 100:.3f}¢ ({sj['jev_cost'] * 100:.4f}¢) | {nblk} of {nchk} |")
    md.append("")
    open(os.path.join(ROOT, "tables_full.md" if FULL else "tables.md"), "w").write("\n".join(md))
    if FULL:
        print("wrote tables_full.md")
        return

    # ---- charts ----
    def pts(getter, include_jev=False):
        out = []
        for m in models:
            for arm in (("none", "jev") if include_jev else ("none",)):
                s = getter(m, arm)
                if s and s["n"]:
                    kind = "jev" if arm == "jev" else ("closed" if M.MODELS[m][4].startswith("closed") else "open")
                    out.append((label(m) + (" + Jev" if arm == "jev" else ""), s["cost_per_success"], s["success"], kind))
        return out
    svg_chart(pts(lambda m, arm: S.get(m) if arm == "none" and m in S else None),
              "All ten use cases: success vs cost per successful task", os.path.join(ROOT, "charts", "overall.svg"))
    for u in UCS:
        svg_chart(pts(lambda m, arm, u=u: stats(data[(u, m, arm)]) if (u, m, arm) in data else None, include_jev=True),
                  f"{NAMES[u]}: success vs cost per successful task", os.path.join(ROOT, "charts", f"{u}.svg"))
    print("wrote results.csv, tables.md, charts/")


if __name__ == "__main__":
    main()
