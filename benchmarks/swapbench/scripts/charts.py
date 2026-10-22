"""Charts for the write-up, as standalone SVG (no plotting dependency), from results/runs/.

  python scripts/charts.py --out docs/img        (tau2 venv; reuses scripts/headline.py)
"""
import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(HERE))
import headline as H  # noqa: E402
from swapbench import stats  # noqa: E402

INK, MUTED, RULE, BG = "#1d2320", "#66716c", "#d9dfdc", "#ffffff"
RED, GREEN, AMBER, TEAL = "#b23a2a", "#2d7a45", "#a96f00", "#11665a"
FONT = "font-family='-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif'"


def svg(w, h, body):
    return (f"<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 {w} {h}' width='{w}' height='{h}' {FONT}>"
            f"<rect width='{w}' height='{h}' fill='{BG}'/>{body}</svg>")


def text(x, y, s, size=12, fill=INK, anchor="start", weight="normal"):
    s = str(s).replace("&", "&amp;").replace("<", "&lt;")
    return f"<text x='{x:.1f}' y='{y:.1f}' font-size='{size}' fill='{fill}' text-anchor='{anchor}' font-weight='{weight}'>{s}</text>"


def candidates():
    """Per candidate: domain, name, next-step gap to self-agreement (pts), hidden-set delta (pts), truth."""
    man = json.load(open(os.path.join(H.RES, "manifest.json")))
    out = []
    for dom, d in man.items():
        inc = d["incumbent"]
        self_ns = H.nextstep(dom, inc)
        inc_test = H.rows(dom, inc, {"test"})
        for run in d["runs"]:
            if run == inc or run in H.SKIP_VERIFY:
                continue
            ns = H.nextstep(dom, run)
            if not ns:
                continue
            t = H.rows(dom, run, {"test"})
            q, h = stats.paired_delta(t, inc_test), stats.paired_delta(t, inc_test, "harmful_writes")
            out.append({"dom": dom, "run": run, "gap": (ns[0] - self_ns[0]) * 100, "delta": q["delta"] * 100,
                        "truth": stats.truth_label(q, h, 0.05)})
    return out


def scatter(cs, path):
    """Two aligned panels per candidate: what next-step agreement said, and what happened on the hidden set."""
    cs = sorted(cs, key=lambda c: -c["gap"])
    row, T, B, L = 30, 70, 74, 230
    W = 760
    Hh = T + row * len(cs) + B
    pa, pb = (L, L + 210), (L + 260, W - 20)          # panel x-ranges
    xa, xb = (-14, 2), (-16, 4)                      # value ranges (pts); off-scale values get an arrow
    XA = lambda v: pa[0] + (min(max(v, xa[0]), xa[1]) - xa[0]) / (xa[1] - xa[0]) * (pa[1] - pa[0])  # noqa: E731
    XB = lambda v: pb[0] + (min(max(v, xb[0]), xb[1]) - xb[0]) / (xb[1] - xb[0]) * (pb[1] - pb[0])  # noqa: E731
    col = {"REGRESSED": RED, "NON-INFERIOR": GREEN, "AMBIGUOUS": AMBER}
    b = [text(20, 24, "Next-step agreement approved swaps that were worse for customers", 15, weight="bold"),
         text(20, 44, "Each row is a candidate swap. Colour = truth on 240 hidden scenarios.", 11.5, MUTED)]
    for (x0, x1), X, rng, title, cut in ((pa, XA, xa, "next-step agreement − self-agreement (pts)", -5),
                                         (pb, XB, xb, "hidden-set success vs incumbent (pts)", -5)):
        b.append(text((x0 + x1) / 2, T - 8, title, 11, MUTED, "middle"))
        for v in range(rng[0], rng[1] + 1, 4 if X is XA else 5):
            b.append(f"<line x1='{X(v):.1f}' x2='{X(v):.1f}' y1='{T}' y2='{Hh - B}' stroke='{RULE}'/>"
                     + text(X(v), Hh - B + 15, v, 10.5, MUTED, "middle"))
        b.append(f"<line x1='{X(cut):.1f}' x2='{X(cut):.1f}' y1='{T}' y2='{Hh - B}' stroke='{INK}' stroke-dasharray='4 3'/>")
    b.append(text(XA(-5) + 4, Hh - B + 30, "SAFE to the right of the line", 10.5, INK))
    b.append(text(XB(-5) + 4, Hh - B + 30, "worse than −5: regressed", 10.5, INK))
    for i, c in enumerate(cs):
        y = T + i * row + row / 2
        if i % 2 == 0:
            b.append(f"<rect x='10' y='{y - row / 2}' width='{W - 20}' height='{row}' fill='#f4f6f5'/>")
        b.append(text(L - 12, y + 4, f"{c['run']} · {c['dom']}", 11.5, INK, "end"))
        for X, v, rng in ((XA, c["gap"], xa), (XB, c["delta"], xb)):
            b.append(f"<circle cx='{X(v):.1f}' cy='{y:.1f}' r='6' fill='{col[c['truth']]}'/>")
            if v < rng[0]:
                b.append(text(X(v) + 10, y + 4, f"◂ {v:.0f}", 10.5, MUTED))
    lx = 20
    for k, v in col.items():
        b.append(f"<circle cx='{lx + 6}' cy='{Hh - 14}' r='5' fill='{v}'/>" + text(lx + 16, Hh - 10, k.lower(), 11, MUTED))
        lx += 120
    open(path, "w").write(svg(W, Hh, "".join(b)))


def sweep(cs, path):
    W, Hh, L, R, T, B = 720, 330, 60, 150, 58, 50
    ths = list(range(0, 21))
    rowsv = []
    for th in ths:
        fs = fa = 0
        for c in cs:
            safe = c["gap"] >= -th
            fs += safe and c["truth"] == "REGRESSED"
            fa += (not safe) and c["truth"] == "NON-INFERIOR"
        rowsv.append((th, fs, fa))
    ymax = 7
    X = lambda v: L + v / 20 * (W - L - R)  # noqa: E731
    Y = lambda v: T + (ymax - v) / ymax * (Hh - T - B)  # noqa: E731
    b = [text(L, 22, "No next-step threshold avoids both errors", 15, weight="bold")]
    for v in range(0, ymax + 1):
        b.append(f"<line x1='{L}' x2='{W - R}' y1='{Y(v)}' y2='{Y(v)}' stroke='{RULE}'/>" + text(L - 8, Y(v) + 4, v, 11, MUTED, "end"))
    for v in range(0, 21, 5):
        b.append(text(X(v), Hh - B + 16, v, 11, MUTED, "middle"))
    for idx, colr, name in ((1, RED, "false SAFE (regressed swaps approved)"), (2, AMBER, "false alarms (good swaps rejected)")):
        pts = " ".join(f"{X(r[0]):.1f},{Y(r[idx]):.1f}" for r in rowsv)
        b.append(f"<polyline points='{pts}' fill='none' stroke='{colr}' stroke-width='2.5' stroke-linejoin='round'/>")
        for r in rowsv:
            b.append(f"<circle cx='{X(r[0]):.1f}' cy='{Y(r[idx]):.1f}' r='3' fill='{colr}'/>")
        b.append(text(W - R + 10, Y(rowsv[-1][idx]) + 4, name.split(" (")[0], 11, colr))
    b.append(text((L + W - R) / 2, Hh - 14, "threshold: SAFE if agreement ≥ self-agreement − threshold (pts)", 12, MUTED, "middle"))
    regressed = sum(c["truth"] == "REGRESSED" for c in cs)
    good = sum(c["truth"] == "NON-INFERIOR" for c in cs)
    b.append(text(L, 40, f"{len(cs)} candidate swaps with next-step data: {regressed} regressed, {good} non-inferior, "
                         f"{len(cs) - regressed - good} ambiguous (truth on the hidden set)", 11.5, MUTED))
    open(path, "w").write(svg(W, Hh, "".join(b)))


def tally(path):
    """Verdict outcomes per verifier, read from experiments/headline.md (generated by headline.py)."""
    rows_ = []
    md = open(os.path.join(os.path.dirname(HERE), "experiments", "headline.md")).read()
    sec = md.split("### Tally")[1].split("##")[0]
    for line in sec.strip().splitlines()[2:]:
        p = [x.strip() for x in line.strip("|").split("|")]
        rows_.append((p[0], int(p[2]), int(p[3]), int(p[4]), int(p[5]), int(p[6])))
    W, Hh, L, R, T = 720, 230, 110, 30, 50
    bw = W - L - R
    n = sum(rows_[0][1:])
    b = [text(L - 100, 22, "Verdicts on 13 candidate swaps (2 domains)", 15, weight="bold")]
    cols = [(GREEN, "correct"), (RED, "false SAFE"), (AMBER, "false alarm"), ("#8b9691", "not enough evidence"), ("#cfd6d2", "truth ambiguous")]
    for i, r in enumerate(rows_):
        y = T + i * 52
        b.append(text(L - 10, y + 21, r[0], 12, INK, "end", "bold"))
        x = L
        for (c, _), v in zip(cols, r[1:]):
            w = v / n * bw
            if v:
                b.append(f"<rect x='{x:.1f}' y='{y}' width='{max(w - 2, 0):.1f}' height='32' fill='{c}' rx='3'/>")
                b.append(text(x + w / 2, y + 21, v, 12, "#ffffff" if c not in ("#cfd6d2",) else INK, "middle", "bold"))
            x += w
    lx = L
    for c, name in cols:
        b.append(f"<rect x='{lx}' y='{Hh - 26}' width='12' height='12' fill='{c}' rx='2'/>" + text(lx + 16, Hh - 16, name, 11, MUTED))
        lx += 22 + len(name) * 6.2
    open(path, "w").write(svg(W, Hh, "".join(b)))


def fixloop(path):
    runs = [("GPT-5 (incumbent)", "gpt-5", TEAL), ("Qwen, stock", "qwen27b-bf16", RED), ("Qwen + guardrails", "qwen27b-guards", RED),
            ("Qwen + guardrails + policy fix", "qwen27b-fixed", GREEN)]
    vals = []
    for label, run, c in runs:
        t = H.rows("fintech", run, {"test"})
        vals.append((label, H.mean_ci(t, "harmful_writes"), H.mean_ci(t, "reward"), c))
    W, Hh, L, R, T = 760, 250, 230, 190, 50
    xmax = 0.14
    X = lambda v: L + v / xmax * (W - L - R)  # noqa: E731
    b = [text(20, 22, "Harmful actions per conversation, fintech hidden set (95% CI)", 15, weight="bold")]
    for v in (0, 0.04, 0.08, 0.12):
        b.append(f"<line x1='{X(v)}' x2='{X(v)}' y1='{T - 6}' y2='{Hh - 34}' stroke='{RULE}'/>" + text(X(v), Hh - 18, f"{v:.2f}", 11, MUTED, "middle"))
    for i, (label, h, s, c) in enumerate(vals):
        y = T + i * 44
        b.append(text(L - 10, y + 17, label, 12, INK, "end"))
        b.append(f"<rect x='{L}' y='{y + 4}' width='{X(h[0]) - L:.1f}' height='20' fill='{c}' rx='0'/>")
        b.append(f"<line x1='{X(h[1]):.1f}' x2='{X(h[2]):.1f}' y1='{y + 14}' y2='{y + 14}' stroke='{INK}' stroke-width='1.5'/>")
        b.append(text(X(max(h[2], h[0])) + 8, y + 18, f"{h[0]:.3f} · success {s[0] * 100:.1f}%", 11, INK))
    open(path, "w").write(svg(W, Hh, "".join(b)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    cs = candidates()
    scatter(cs, os.path.join(a.out, "nextstep_vs_outcome.svg"))
    sweep(cs, os.path.join(a.out, "threshold_sweep.svg"))
    tally(os.path.join(a.out, "verdict_tally.svg"))
    fixloop(os.path.join(a.out, "fix_loop.svg"))
    print("wrote", sorted(os.listdir(a.out)))


if __name__ == "__main__":
    main()
