"""Regenerate every published table from the committed per-case rows and compare with the committed files.

  python scripts/check_tables.py      # needs env/tasks.json (scripts/fetch_data.sh); no model calls, no network

Works on a temporary copy, so the committed results stay as published. Checks:
1. harness/report.py --ref opus-5.5 (first prompt, 252 cases) against results/tables.md. report.py draws its bootstrap
   intervals from one random stream in the order glob() lists results/runs/, which depends on the filesystem; the
   check feeds the files in the original run's order (the key order of results/summary.json) so the intervals can match.
2. harness/tuned_report.py (held-out arms) against results/tuned/summary.json.
3. scripts/export.py against results/underwriting.json.
4. Spend recorded in the rows against the spend log (RERUN.md section 7).
Prints every difference; exits 1 if any check differs.
"""
import difflib
import glob
import json
import os
import runpy
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
COPY = ["harness/report.py", "harness/tuned_report.py", "env/split.json", "env/tasks.json", "results/runs",
        "results/tuned/runs", "results/tuned/hillclimb", "results/summary.json"]


def copy_tree(dst):
    for rel in COPY:
        src, out = os.path.join(ROOT, rel), os.path.join(dst, rel)
        os.makedirs(os.path.dirname(out), exist_ok=True)
        (shutil.copytree if os.path.isdir(src) else shutil.copy)(src, out)


def run_report_in_original_order(tmp):
    order = list(json.load(open(os.path.join(ROOT, "results", "summary.json")))["models"])
    real = glob.glob

    def ordered(pat, *a, **k):
        out = real(pat, *a, **k)
        if pat.endswith(os.path.join("runs", "*.jsonl")) and "tuned" not in pat:
            out.sort(key=lambda p: order.index(os.path.basename(p)[:-6]))
        return out

    glob.glob = ordered
    argv, stdout = sys.argv, sys.stdout
    sys.argv, sys.stdout = [os.path.join(tmp, "harness", "report.py"), "--ref", "opus-5.5"], open(os.devnull, "w")
    try:
        runpy.run_path(sys.argv[0], run_name="__main__")
    finally:
        sys.argv, sys.stdout, glob.glob = argv, stdout, real


def show_diff(name, a, b):
    d = list(difflib.unified_diff(a.splitlines(), b.splitlines(), "published", "regenerated", lineterm="", n=0))
    print(f"[{'same' if not d else 'DIFFERS'}] {name}")
    for line in d[2:]:
        print("    " + line)
    return not d


def deep_diff(a, b, path=""):
    if isinstance(a, dict) and isinstance(b, dict):
        return [x for k in sorted(set(a) | set(b), key=str) for x in (
            [f"{path}.{k}: only in one file"] if (k in a) != (k in b) else deep_diff(a[k], b[k], f"{path}.{k}"))]
    if isinstance(a, list) and isinstance(b, list) and len(a) == len(b):
        return [x for i, (p, q) in enumerate(zip(a, b)) for x in deep_diff(p, q, f"{path}[{i}]")]
    return [] if a == b else [f"{path}: {str(a)[:90]} -> {str(b)[:90]}"]


def main():
    ok = True
    with tempfile.TemporaryDirectory() as tmp:
        copy_tree(tmp)
        run_report_in_original_order(tmp)
        ok &= show_diff("first prompt, 252 cases: results/tables.md",
                        open(os.path.join(ROOT, "results", "tables.md")).read(),
                        open(os.path.join(tmp, "results", "tables.md")).read())
        subprocess.run([sys.executable, os.path.join(tmp, "harness", "tuned_report.py")], check=True,
                       stdout=subprocess.DEVNULL)
        d = deep_diff(json.load(open(os.path.join(ROOT, "results", "tuned", "summary.json"))),
                      json.load(open(os.path.join(tmp, "results", "tuned", "summary.json"))))
        print(f"[{'same' if not d else 'DIFFERS'}] held-out arms: results/tuned/summary.json")
        ok &= not d
        for line in d:
            print("    " + line)
        out = os.path.join(tmp, "underwriting.json")
        subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "export.py"), out], check=True,
                       stdout=subprocess.DEVNULL)
        d = deep_diff(json.load(open(os.path.join(ROOT, "results", "underwriting.json"))), json.load(open(out)))
        print(f"[{'same' if not d else 'DIFFERS'}] export: results/underwriting.json")
        ok &= not d
        for line in d:
            print("    " + line)

    def spend(pattern, skip=None):
        total = 0.0
        for p in glob.glob(os.path.join(ROOT, pattern)):
            if skip and skip in p:
                continue
            for line in open(p):
                r = json.loads(line)
                total += r.get("cost", 0) + r.get("sim_cost", 0) + r.get("judge_cost", 0)
        return total

    opt = sum(json.load(open(p))["optimizer_cost"] for p in glob.glob(os.path.join(ROOT, "results/tuned/hillclimb/*.json")))
    for name, got, logged in [
        ("first run, all rows incl. superseded re-runs", spend("results/runs/*.jsonl"), 79.49),
        ("tuning rounds, tuned, effort, repeat + optimizer", spend("results/tuned/runs/*.jsonl", "__shared") + opt, 85.63),
        ("shared prompt", spend("results/tuned/runs/*__shared.jsonl"), 47.38),
        ("self-judge regrade", json.load(open(os.path.join(ROOT, "results", "regrade_self.json")))["spend"], 2.01),
        ("memorization probe", sum(r["cost"] for v in json.load(open(os.path.join(ROOT, "results", "probe.json"))).values()
                                   for r in v["rows"]), 1.43)]:
        same = round(got, 2) == logged
        ok &= same
        print(f"[{'same' if same else 'DIFFERS'}] spend, {name}: rows ${got:.2f}, log ${logged:.2f}")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
