"""
Rebuild results and meta.total_spend_usd of results/sglang-vs-vllm.json from the published rows
(results/runs/bench.jsonl: one summary per run; results/runs/bench-<name>.json: every request's
timing and token usage, no prompts) and compare with the committed export. No network, no GPU.

    python scripts/rebuild_export.py

Same computation as the original export script (benchmarks-export/scripts/build_sglang.py).
Exit code 0 and "ALL MATCH" when every rebuilt value equals the committed one.
"""
import json
import sys
from pathlib import Path

BENCH = Path(__file__).resolve().parents[1]
RUNS = BENCH / "results" / "runs"
NAME = {"rb-vllm": "stock vLLM", "rb-sglang": "stock SGLang",
        "rb-sglang-lazy": "SGLang, lazy radix + bf16 states", "rb-sglang-noradix": "SGLang, radix cache off"}


def build():
    recs = [json.loads(l) for l in open(RUNS / "bench.jsonl") if l.strip()]
    results = {}
    for r in recs:
        res = json.load(open(RUNS / f"bench-{r['name']}.json"))["results"]
        ok = [x for x in res if not x["error"] and x.get("usage")]
        errs = [x for x in res if x["error"]]
        gen = sum(x["usage"]["completion_tokens"] for x in ok)
        prompt = sum(x["usage"]["prompt_tokens"] for x in ok)
        results[NAME[r["name"]]] = [{
            "model": "Qwen/Qwen3.8-27B",
            "n": len(res), "n_definition": "requests sent",
            "correct": None, "accuracy": None, "ci95": None, "cost_per_correct_cents": None,
            "requests_completed": len(ok), "requests_errored": len(errs),
            "error_types": sorted({e["error"].split("(")[0] for e in errs}),
            "sessions_touched": len({x["trial"] for x in res}),
            "measured_window_s": round(r["duration_s"], 1),
            "generated_tokens": gen, "prompt_tokens": prompt,
            "generated_tokens_per_s": round(r["gen_tok_per_s"], 2),
            "request_latency_p50_s": round(r["latency_p50_s"], 2), "request_latency_p90_s": round(r["latency_p90_s"], 2),
            "ttft_p50_s": round(r["ttft_p50_s"], 2), "time_per_output_token_p50_ms": round(r["tpot_p50_ms"], 2),
            "client_prefix_cache_hit": round(r["client_cache_hit"], 4),
            "prompt_tokens_vs_recorded_median": round(r["prompt_vs_recorded"], 4),
            "kv_or_token_usage_peak": r["kv_peak"], "running_requests_peak": r["running_peak"],
            "waiting_requests_peak": r["waiting_peak"],
            "server_startup_s": round(r["startup_s"], 1),
            "gpu_cost_usd": round(r["cost"], 4),
            "mean_tokens_per_case": round((gen + prompt) / len(ok), 1),
            "mean_calls_per_case": None,
            "failures": {e.split("(")[0]: sum(1 for x in errs if x["error"].split("(")[0] == e.split("(")[0])
                         for e in {x["error"] for x in errs}} if errs else {},
        }]
        # Recompute the run summary from the per-request rows as a cross-check of bench.jsonl.
        assert len(ok) == r["requests_ok"] and len(res) - len(ok) == r["errors"], r["name"]
        assert abs(gen / r["duration_s"] - r["gen_tok_per_s"]) < 1e-6, r["name"]
    v = results["stock vLLM"][0]
    for e in results.values():
        e[0]["requests_completed_vs_vllm"] = round(e[0]["requests_completed"] / v["requests_completed"], 4)
        e[0]["generated_tokens_per_s_vs_vllm"] = round(e[0]["generated_tokens_per_s"] / v["generated_tokens_per_s"], 4)
    return results, round(sum(r["cost"] for r in recs), 4)


def main():
    results, total = build()
    exp = json.load(open(BENCH / "results" / "sglang-vs-vllm.json"))
    problems = []
    for k in sorted(set(results) | set(exp["results"])):
        a, b = results.get(k, [{}])[0], exp["results"].get(k, [{}])[0]
        for f in sorted(set(a) | set(b)):
            if a.get(f) != b.get(f):
                problems.append(f"results[{k}].{f}: rebuilt {a.get(f)!r} != export {b.get(f)!r}")
    if total != exp["meta"]["total_spend_usd"]:
        problems.append(f"meta.total_spend_usd: rebuilt {total} != export {exp['meta']['total_spend_usd']}")
    for k, e in results.items():
        e = e[0]
        print(f"{k}: {e['requests_completed']}/{e['n']} requests, {e['generated_tokens_per_s']} gen tok/s "
              f"({e['generated_tokens_per_s_vs_vllm']} of vLLM), p50 {e['request_latency_p50_s']} s, "
              f"peak running {e['running_requests_peak']}, errors {e['requests_errored']}")
    print(f"total spend ${total}")
    if problems:
        print(f"{len(problems)} MISMATCHES:\n" + "\n".join(problems))
        sys.exit(1)
    print("ALL MATCH")


if __name__ == "__main__":
    main()
