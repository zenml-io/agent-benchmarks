"""Publication step for the SwapBench export (results/swapbench.json): sets the public-safety section.

Per-provider results (the same open model on several commercial inference providers, and the experiments run on
hosted models) are withheld pending provider review; build_export.py leaves them out. Rebuilding from results/runs/
must reproduce results/swapbench.json exactly.
"""


def publish(out):
    out["public_safety"] = [
        {"item": "Per-provider results", "why": "The providers have not reviewed them. The same-model-on-four-providers runs, the experiments on hosted models (Jev gate, decomposition, outcome-trained check) and their prices are left out of this file, the rows and the docs; the harness (scripts/provider_runs.sh, scripts/providers.py) stays so others can run their own providers.",
         "where_in_file": "not in file", "status": "withheld"},
        {"item": "Draft status of the write-up", "why": "docs/WRITEUP.md is a draft for a public page and has not been reviewed for publication.",
         "where_in_file": "meta (sources only)", "status": "flagged"},
        {"item": "Hidden sets v1 and v2 and their seeds", "why": "v2 is the secret leaderboard set (not used for any number here); v1, behind every number, is kept private so the numbers can be re-checked on untouched data. Only hashes and counts appear.",
         "where_in_file": "not in file", "status": "not included"},
        {"item": "Local checkpoint name of the fine-tuned model", "why": "Internal artifact path; only the config label is given.",
         "where_in_file": "models[id=qwen27b-rft]", "status": "not included"},
    ]
    out["dataset"]["license"] = "Apache-2.0"
    out["dataset"]["license_note"] = ("This repository is Apache-2.0 (root LICENSE). The tau2-bench retail world (catalogue, base "
                                      "users and orders) stays under tau2-bench's MIT licence, which requires keeping its copyright notice.")
    return out
