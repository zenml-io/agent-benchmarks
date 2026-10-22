"""Build REPORT.md and results/report.html from results/summary.json (run harness/report.py --ref opus-5.5 first).

  python harness/build_report.py
"""
import html
import json
import math
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
S = json.load(open(os.path.join(ROOT, "results", "summary.json")))["models"]
PROBE = json.load(open(os.path.join(ROOT, "results", "probe.json")))
NAMES = {"opus-5.5": "Claude Opus 5.5", "sonnet-5.5": "Claude Sonnet 5.5", "haiku-5.5": "Claude Haiku 5.5",
         "gpt-6.1-sol": "GPT-6.1 Sol", "gpt-6-luna": "GPT-6 Luna", "deepseek-v4-pro@provider-a": "DeepSeek V4 Pro",
         "deepseek-v4.1-flash@provider-a": "DeepSeek V4.1 Flash", "glm-5.3@provider-a": "GLM 5.3",
         "glm-5.3-flash@provider-a": "GLM 5.3 Flash", "gpt-oss-120b@provider-a": "gpt-oss-120b",
         "qwen3.8-27b@provider-a": "Qwen3.8 27B", "minimax-m3@provider-a": "MiniMax-M3"}
OPEN = {k for k in NAMES if "@" in k}
TYPES = [("Appetite Check", "Appetite"), ("Product Recommendations", "Other products"),
         ("Small Business Elibility Check", "Small business"), ("Policy Limits", "Limits"),
         ("Deductibles", "Deductibles"), ("Business Classification", "Classification")]
ORDER = sorted(S, key=lambda m: (-S[m]["accuracy"], S[m]["cost_per_correct"]))


def e(x):
    return html.escape(str(x))


def cents(x):
    return f"{x * 100:.2f}¢"


def pct(x):
    return f"{x * 100:.1f}%"


def vs(m):
    v = S[m].get("vs_ref")
    return "reference" if not v else f"{v['delta'] * 100:+.1f} [{v['lo'] * 100:+.1f}, {v['hi'] * 100:+.1f}]"


def per10k(m):
    return S[m]["cost_per_task"] * 10000, (1 - S[m]["accuracy"]) * 10000


def scatter():
    """Accuracy (with 95% interval) against cost per correct decision, log scale."""
    W, H, L, R, T, B = 760, 440, 64, 24, 24, 56
    xs = [S[m]["cost_per_correct"] * 100 for m in S]
    x0, x1 = math.log10(0.1), math.log10(20)
    y0, y1 = 50, 100
    fx = lambda c: L + (math.log10(c) - x0) / (x1 - x0) * (W - L - R)  # noqa: E731
    fy = lambda a: T + (y1 - a) / (y1 - y0) * (H - T - B)  # noqa: E731
    g = [f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="Accuracy against cost per correct decision">']
    for a in range(50, 101, 10):
        g.append(f'<line x1="{L}" x2="{W - R}" y1="{fy(a):.1f}" y2="{fy(a):.1f}" class="grid"/>'
                 f'<text x="{L - 8}" y="{fy(a) + 4:.1f}" class="tick" text-anchor="end">{a}%</text>')
    for c, lab in [(0.1, "0.1¢"), (0.3, "0.3¢"), (1, "1¢"), (3, "3¢"), (10, "10¢")]:
        g.append(f'<line x1="{fx(c):.1f}" x2="{fx(c):.1f}" y1="{T}" y2="{H - B}" class="grid"/>'
                 f'<text x="{fx(c):.1f}" y="{H - B + 18}" class="tick" text-anchor="middle">{lab}</text>')
    g.append(f'<text x="{(L + W - R) / 2:.0f}" y="{H - 10}" class="axis" text-anchor="middle">'
             f'Cost per correct decision (log scale)</text>')
    g.append(f'<text x="16" y="{(T + H - B) / 2:.0f}" class="axis" text-anchor="middle" '
             f'transform="rotate(-90 16 {(T + H - B) / 2:.0f})">Correct decisions</text>')
    offsets = {"opus-5.5": (8, -8, "start"), "deepseek-v4-pro@provider-a": (-8, -8, "end"),
               "glm-5.3@provider-a": (8, 14, "start"), "glm-5.3-flash@provider-a": (-8, -8, "end"),
               "deepseek-v4.1-flash@provider-a": (10, -16, "start"), "sonnet-5.5": (8, 4, "start"),
               "haiku-5.5": (8, -8, "start"), "gpt-6-luna": (8, 4, "start"), "minimax-m3@provider-a": (-10, 16, "end"),
               "qwen3.8-27b@provider-a": (8, 4, "start"), "gpt-6.1-sol": (-8, 16, "end"),
               "gpt-oss-120b@provider-a": (8, 4, "start")}
    for m in S:
        s = S[m]
        cx, cy = fx(s["cost_per_correct"] * 100), fy(s["accuracy"] * 100)
        lo, hi = s["ci"]
        cls = "open" if m in OPEN else "closed"
        g.append(f'<line x1="{cx:.1f}" x2="{cx:.1f}" y1="{fy(lo * 100):.1f}" y2="{fy(hi * 100):.1f}" class="bar {cls}"/>')
        shape = (f'<rect x="{cx - 5:.1f}" y="{cy - 5:.1f}" width="10" height="10" class="{cls}"/>' if m in OPEN
                 else f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="5.5" class="{cls}"/>')
        g.append(f'<g>{shape}<title>{e(NAMES[m])}: {pct(s["accuracy"])}, {cents(s["cost_per_correct"])} per correct '
                 f'decision</title></g>')
        dx, dy, anc = offsets.get(m, (8, 4, "start"))
        g.append(f'<text x="{cx + dx:.1f}" y="{cy + dy:.1f}" class="lbl" text-anchor="{anc}">{e(NAMES[m])}</text>')
    g.append("</svg>")
    return "".join(g)


def table_html():
    rows = []
    for m in ORDER:
        s = S[m]
        lo, hi = s["ci"]
        cost10k, wrong10k = per10k(m)
        rows.append(f'<tr><td>{e(NAMES[m])} <span class="tag">{"open" if m in OPEN else "closed"}</span></td>'
                    f'<td class="n">{pct(s["accuracy"])} <span class="ci">({lo * 100:.0f}–{hi * 100:.0f})</span></td>'
                    f'<td class="n">{vs(m)}</td><td class="n">{cents(s["cost_per_correct"])}</td>'
                    f'<td class="n">${cost10k:,.0f}</td><td class="n">{wrong10k:,.0f}</td>'
                    f'<td class="n">{s["latency_p50"]:.0f}s</td></tr>')
    return ('<div class="scroll"><table><thead><tr><th>Model</th><th class="n">Correct (95% CI)</th>'
            '<th class="n">vs Opus 5.5, pts [95% CI]</th><th class="n">Cost per correct decision</th>'
            '<th class="n">Cost per 10,000 decisions</th><th class="n">Wrong per 10,000</th>'
            '<th class="n">Median time</th></tr></thead><tbody>' + "".join(rows) + "</tbody></table></div>")


def types_html():
    head = "".join(f'<th class="n">{e(lab)}</th>' for _, lab in TYPES)
    rows = []
    for m in ORDER:
        bt = S[m]["by_type"]
        cells = "".join(f'<td class="n{" low" if bt[t]["accuracy"] < 0.8 else ""}">{bt[t]["accuracy"] * 100:.0f}%</td>'
                        for t, _ in TYPES)
        rows.append(f"<tr><td>{e(NAMES[m])}</td>{cells}</tr>")
    counts = " · ".join(f'{lab} {S[ORDER[0]]["by_type"][t]["n"]}' for t, lab in TYPES)
    return (f'<div class="scroll"><table><thead><tr><th>Model</th>{head}</tr></thead><tbody>{"".join(rows)}'
            f'</tbody></table></div><p class="small">Tasks per type: {counts}. Shaded: below 80%.</p>')


def main():
    page = open(os.path.join(ROOT, "harness", "report_template.html")).read()
    tasks = {t["id"]: t["task"] for t in json.load(open(os.path.join(ROOT, "env", "tasks.json")))}
    probe = {}
    for v in PROBE.values():
        for r in v["rows"]:
            if r["correct"] is not None:
                c = probe.setdefault(tasks[r["task"]], [0, 0])
                c[0] += bool(r["correct"])
                c[1] += 1
    vals = dict(scatter=scatter(), table=table_html(), types=types_html(),
                probe_app=f"{probe['Appetite Check'][0]} of {probe['Appetite Check'][1]}",
                probe_products=f"{probe['Product Recommendations'][0]} of {probe['Product Recommendations'][1]}")
    for k, v in vals.items():
        page = page.replace("@@" + k + "@@", v)
    assert "@@" not in page, [x for x in page.split("@@")[1::2]]
    open(os.path.join(ROOT, "results", "report.html"), "w").write(page)
    print("wrote results/report.html")


if __name__ == "__main__":
    main()
