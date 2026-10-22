"""Strip a step-check output directory (swap_run.py --out DIR) down to what may be published.

  python scripts/strip_step_check.py SRC_DIR DST_DIR

The Exgentic dataset declares no license, so recorded content (the recorded tool arguments and
text, and the disagreement examples that quote it) stays out. What remains is enough to rebuild
every published step-check number:

- calls.jsonl: one row per (call, candidate, attempt) with the agreement label, cost, the recorded
  tool names (`recorded_tools`), and the reply's tool names, failure label and latency. Recorded
  arguments, recorded text, reply text and reply arguments are dropped.
- report.json: the analyzer report without `disagreements` (recorded and reply content), without
  candidates' `failure_examples`, and with non-OpenAI endpoint hosts replaced by a neutral label.
  insights.json (the report rendered as text cards, with quoted disagreements) is not copied.
"""
import json
import os
import sys

LABELS = {}  # endpoint host -> neutral label, assigned in order of first appearance


def neutral(host):
    if host in (None, "api.openai.com"):
        return host
    return LABELS.setdefault(host, f"provider-{chr(ord('a') + len(LABELS))}")


def main(src, dst):
    os.makedirs(dst, exist_ok=True)
    rep = json.load(open(os.path.join(src, "report.json")))
    rep.pop("disagreements", None)
    for c in rep["candidates"]:
        c.pop("failure_examples", None)
        c["endpoint_host"] = neutral(c.get("endpoint_host"))
    with open(os.path.join(dst, "report.json"), "w") as f:
        json.dump(rep, f, indent=1)
        f.write("\n")
    with open(os.path.join(src, "calls.jsonl")) as fin, open(os.path.join(dst, "calls.jsonl"), "w") as fout:
        for line in fin:
            r = json.loads(line)
            rep_ = r.get("reply")
            fout.write(json.dumps({
                "run": r["run"], "node": r["node"], "candidate": r["candidate"], "attempt": r["attempt"],
                "not_run": r["not_run"], "agreement": r["agreement"], "cost": r["cost"],
                "recorded_tools": [t[0] for t in r["recorded"]],
                "reply": None if rep_ is None else {"tools": [t[0] for t in rep_["tools"]], "failure": rep_["failure"],
                                                    "latency": rep_["latency"]},
            }) + "\n")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
