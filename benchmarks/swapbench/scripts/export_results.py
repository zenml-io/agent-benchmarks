"""Export compact per-conversation results (no transcripts) into results/runs/, from a manifest.

  python scripts/export_results.py <manifest.json> [--root <dir the manifest's paths are relative to>]   (tau2 venv)

Manifest: {"domains": {"<domain>": {"incumbent": "<run>", "runs": {"<run>": {"dir": "<dir with split/results.json>",
"splits": {"test": "<optional explicit path>"}, "nextstep": "<optional nextstep json>", "note": "..."}}}}}.
Writes results/runs/<domain>/<run>.jsonl (one row per conversation) and results/runs/<domain>/<run>.nextstep.jsonl.
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from swapbench import tau2_adapter  # noqa: E402

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "results", "runs")
KEEP = ("scenario", "trial", "reward", "harmful_writes", "writes", "tool_calls", "agent_calls", "cost_usd",
        "input_tokens", "cached_tokens", "output_tokens", "reasoning_tokens", "termination", "infra_error", "duration_s")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("manifest")
    ap.add_argument("--root", default="")
    a = ap.parse_args()
    man = json.load(open(a.manifest))
    for dom, d in man["domains"].items():
        os.makedirs(os.path.join(OUT, dom), exist_ok=True)
        for run, spec in d["runs"].items():
            n = 0
            with open(os.path.join(OUT, dom, f"{run}.jsonl"), "w") as f:
                for split in ("train", "pool", "test"):
                    p = spec.get("splits", {}).get(split) or os.path.join(spec["dir"], split, "results.json")
                    p = os.path.join(a.root, p)
                    if not os.path.exists(p):
                        continue
                    for e in tau2_adapter.load(p, domain=dom):
                        row = {k: e[k] for k in KEEP}
                        row.update(split=split, model=e["model"], user_model=e["user_model"],
                                   customer_turns=sum(m["role"] == "user" for m in e["messages"]),
                                   agent_turns=sum(m["role"] == "assistant" for m in e["messages"]))
                        f.write(json.dumps(row) + "\n")
                        n += 1
            ns = spec.get("nextstep")
            if ns:
                j = json.load(open(os.path.join(a.root, ns)))
                with open(os.path.join(OUT, dom, f"{run}.nextstep.jsonl"), "w") as f:
                    f.write(json.dumps({"summary": j["summary"]}) + "\n")
                    for r in j["rows"]:
                        f.write(json.dumps({k: r.get(k) for k in ("scenario", "step", "kind", "tool", "write", "exact",
                                                                  "name_match", "cand_tool")}) + "\n")
            print(dom, run, n, "conversations", "+ nextstep" if ns else "")
    json.dump({dom: {"incumbent": d["incumbent"], "runs": {r: {"note": s.get("note", "")} for r, s in d["runs"].items()}}
               for dom, d in man["domains"].items()}, open(os.path.join(OUT, "manifest.json"), "w"), indent=1)


if __name__ == "__main__":
    main()
