"""Extract tasks and the observable environment from Snorkel's underwriting datasets (Apache-2.0).

  python -I env/extract.py data_raw env/extracted.json

Sources (snorkelai on Hugging Face):
  main     Multi-Turn-Insurance-Underwriting, data/train (80 tasks, 380 traces; MCP tools over a SQL database)
  codegen  Multi-Turn-Insurance-Underwriting-Code-Gen (300 tasks, 1800 traces; code interpreter over the same data)
Writes: tasks (id, source, task type, line of business, company profile, reference answer, prior model results),
observed appetite rows, observed SBA size-standard rows, the guidelines text, and each company's NAICS code as used in
the traces Snorkel's judge marked correct (the gold generation needs it, and the datasets do not list it).
"""
import ast
import json
import re
import sys
from collections import Counter, defaultdict

import pandas as pd

APPETITE = re.compile(r'"naics":\s*(\d{6}),\s*"state":\s*"(\w\w)",\s*"lob":\s*"([\w ]+)",\s*"appetite":\s*"(\w+)"')
SBA = re.compile(r'"NAICS Codes":\s*(\d{6}),\s*"Size Standards in millions of dollars":\s*([\d.]+|null|NaN),\s*'
                 r'"Size standards in number of employees":\s*([\d.]+|null|NaN)')
NAICS_ARG = re.compile(r"(?:naics(?:_code)?|NAICS Codes|\"2022 NAICS\"|Code)\s*(?:=|==|IN\s*\(|:)\s*'?(\d{6})", re.I)
FIELDS = ["company name", "annual revenue", "number of employees", "total payroll", "number of vehicles",
          "building construction", "state", "company description", "lob"]


def text_of(step):
    parts = [str(step.get("content") or "")]
    tc = step.get("tool_calls")
    if tc and tc not in ("[]", "null", ""):
        try:
            parts.append(json.dumps(ast.literal_eval(tc)))
        except (ValueError, SyntaxError):
            parts.append(str(tc))
    return "\n".join(parts)


def num(v):
    return None if v in ("null", "NaN") else float(v)


def main(raw, out):
    tasks = {}
    appetite, sba = defaultdict(set), {}
    naics_votes = defaultdict(Counter)
    guidelines = set()
    for source, path in [("main", f"{raw}/data/train-00000-of-00001.parquet"),
                         ("codegen", f"{raw}/codegen/train.parquet")]:
        df = pd.read_parquet(path)
        for _, r in df.iterrows():
            tid = f"{source}-{int(r['company task id'])}"
            t = tasks.setdefault(tid, {
                "id": tid, "source": source, "task": r["task"], "reference": r["reference answer"],
                "company": {k: (v.item() if hasattr(v, "item") else v) for k, v in r[FIELDS].items()},
                "prior": {}})
            t["prior"][r["assistant model name"]] = bool(r["correct"])
            texts = [text_of(s) for s in r["trace"]]
            for tx in texts:
                if source == "main":  # the code-gen environment is a later version; its tables are not mixed in
                    for m in APPETITE.finditer(tx):
                        appetite[(int(m[1]), m[2], m[3])].add(m[4])
                for m in SBA.finditer(tx):
                    sba[int(m[1])] = (num(m[2]), num(m[3]))
                if "***General***" in tx and source == "main":
                    guidelines.add(tx[tx.index("***General***"):].strip())
            if r["correct"]:
                for tx in texts:
                    for m in NAICS_ARG.finditer(tx):
                        naics_votes[tid][int(m[1])] += 1
    # The 100-task file of the main dataset uses the same environment (no conflicting rows); only its appetite rows
    # are used, since its tasks lack the company profile columns.
    for tr in pd.read_parquet(f"{raw}/insurance_underwriting_train_data.parquet")["trace"]:
        for s in tr:
            for m in APPETITE.finditer(text_of(s)):
                if m[3] in ("workers compensation", "property", "general liability", "auto", "cyber", "bop"):
                    appetite[(int(m[1]), m[2], m[3])].add(m[4])
    # Code-gen agents printed the same tables as dataframes. Those rows agree with every overlapping JSON row
    # (checked: 0 conflicts on 144 appetite and 750 SBA overlaps), so they are added for the six LOBs.
    printed_app = re.compile(r"^\s*\d+\s+\d+\s+(\d{6})\s+([A-Z]{2})\s+(workers compensation|property|general liability|"
                             r"auto|cyber|bop)\s+(Yes|No|Qualified)\b", re.M)
    printed_sba = re.compile(r"^\s*\d+\s+\d+\s+(\d{6})\s+([\d.]+|NaN)\s+([\d.]+|NaN)\s*$", re.M)
    for tr in pd.read_parquet(f"{raw}/codegen/train.parquet")["trace"]:
        for s in tr:
            if s.get("type") != "tool":
                continue
            tx = str(s.get("content") or "")
            for m in printed_app.finditer(tx):
                appetite[(int(m[1]), m[2], m[3])].add(m[4])
            if "ize" in tx:
                for m in printed_sba.finditer(tx):
                    sba.setdefault(int(m[1]), (num(m[2]), num(m[3])))
    conflicts = [k for k, v in appetite.items() if len(v) > 1]
    for tid, t in tasks.items():
        m = re.search(r"NAICS code is (\d{6})", t["reference"])
        if m:
            t["naics"], t["naics_source"] = int(m[1]), "reference"
        elif naics_votes[tid]:
            code, votes = naics_votes[tid].most_common(1)[0]
            t["naics"], t["naics_source"] = code, f"correct traces ({votes} mentions)"
        else:
            t["naics"], t["naics_source"] = None, "unknown"
    json.dump({
        "tasks": sorted(tasks.values(), key=lambda t: t["id"]),
        "appetite_rows": [[n, s, l, sorted(v)[0]] for (n, s, l), v in sorted(appetite.items()) if len(v) == 1],
        "appetite_conflicts": [list(k) for k in conflicts],
        "sba_rows": {str(k): v for k, v in sorted(sba.items())},
        "guidelines": sorted(guidelines, key=len)[-1] if guidelines else None,
        "guideline_variants": len(guidelines),
    }, open(out, "w"), indent=1)
    by = Counter((t["source"], t["naics_source"].split(" (")[0]) for t in tasks.values())
    print(f"tasks {len(tasks)}  naics sources {dict(by)}")
    print(f"appetite rows {len(appetite)} (conflicts {len(conflicts)})  sba rows {len(sba)}  "
          f"guideline variants {len(guidelines)}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
