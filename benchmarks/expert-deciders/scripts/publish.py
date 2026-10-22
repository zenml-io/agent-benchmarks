"""Publication step for the expert-deciders export (results/expert-deciders.json).

The agents ran on one commercial inference provider, which no file names. Applied by build_export.py, so rebuilding
from results/runs/ reproduces results/expert-deciders.json exactly.
"""

SUSPENSION = ("the first agent-B live runs on another provider were invalid (85-95% of conversations lost to rate limits and "
              "an account suspension) and were re-run in full.")


def publish(out):
    out["limitations"] = [x.replace(SUSPENSION, "the first agent-B live runs on another provider were invalid (85-95% of "
                                    "conversations lost to our account's limits there) and were re-run in full.")
                          for x in out["limitations"]]
    out["results_note"] = out["results_note"].replace("lost to rate limits and an account suspension",
                                                      "lost to our account's limits on another provider")
    out["dataset"]["license"] = "Apache-2.0"
    out["dataset"]["license_note"] = "This repository is Apache-2.0 (root LICENSE). The bank data is fully synthetic."
    out["public_safety"] = [
        {"item": "Inference provider of agents A and B", "why": "Results are about the checks, not the provider; the provider is not named anywhere (SwapBench's per-provider results are withheld pending provider review).",
         "where_in_file": "results.*[*].inference", "status": "not named"},
        {"item": "Jev price and version", "why": "Jev (TypeSafe) may be named. The $0.042 per 1M input price is an internal assumption with no published source; it is not TypeSafe's list price.",
         "where_in_file": "models[id=jev-latest]; grading.metrics[cost_per_correct_cents]", "status": "flagged"},
        {"item": "Hidden rules text and the interview rubric", "why": "Synthetic bank; published by owner decision (2026-10-22) although they define the test.",
         "where_in_file": "dataset.hidden_rules", "status": "published"},
        {"item": "Hidden sets v1 and v2 and seeds; conversation text, decision-step states and expert explanations", "why": "Derived from the unreleased v1 bank hidden set; only ids, outcomes, counts and scores are published.",
         "where_in_file": "not in file", "status": "not included"},
    ]
    return out
