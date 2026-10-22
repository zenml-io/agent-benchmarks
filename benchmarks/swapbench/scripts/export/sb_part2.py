# executed inside build_export.py: fills models, failures, findings, limitations, public_safety
PD_API = "2026-10-13"
api_note = "Snapshot of litellm's model_cost table pinned in swapbench/pricing.py on 2026-10-13 (dated in the file)."
selfhost_note = "Self-hosted on Modal (vLLM, one H100); no token price. GPU list price in experiments/open_models_retail.md is $3.95/h."
models = [
    dict(id="gpt-5-2025-08-07", display_name="GPT-5", vendor="OpenAI", weights="closed", inference_provider_type="vendor API",
         price_per_mtok_input_usd=1.25, price_per_mtok_output_usd=10.0, price_date=PD_API, price_note=api_note, role="fintech incumbent; arm-1 retail incumbent"),
    dict(id="gpt-5-mini-2025-08-07", display_name="GPT-5 mini", vendor="OpenAI", weights="closed", inference_provider_type="vendor API",
         price_per_mtok_input_usd=0.25, price_per_mtok_output_usd=2.0, price_date=PD_API, price_note=api_note, role="fintech candidate"),
    dict(id="gpt-6-luna", harness_id="openai/responses/gpt-6-luna", display_name="GPT-6 Luna", vendor="OpenAI", weights="closed", inference_provider_type="vendor API",
         price_per_mtok_input_usd=0.10, price_per_mtok_output_usd=0.50, price_date=PD_API, price_note=api_note, role="fintech candidate"),
    dict(id="gpt-5.4-nano", display_name="GPT-5.4 nano", vendor="OpenAI", weights="closed", inference_provider_type="vendor API",
         price_per_mtok_input_usd=0.20, price_per_mtok_output_usd=1.25, price_date=PD_API, price_note=api_note, role="fintech candidate"),
    dict(id="claude-haiku-5-5", harness_id="anthropic/claude-haiku-5-5", display_name="Claude Haiku 5.5", vendor="Anthropic", weights="closed",
         inference_provider_type="vendor API", price_per_mtok_input_usd=0.10, price_per_mtok_output_usd=0.50, price_date=PD_API, price_note=api_note,
         role="retail incumbent; simulated customer in every run"),
    dict(id="Qwen/Qwen3.8-27B", display_name="Qwen3.8-27B (BF16)", vendor="Qwen (Alibaba)", weights="open", inference_provider_type="self-hosted",
         price_per_mtok_input_usd=None, price_per_mtok_output_usd=None, price_date=None, price_note=selfhost_note,
         role="candidate in both domains (configs: qwen27b-bf16, -nothink, -hermes, -guards, -fixed, and base of -rft)"),
    dict(id="Qwen/Qwen3.8-27B-FP8", display_name="Qwen3.8-27B (FP8 checkpoint)", vendor="Qwen (Alibaba)", weights="open", inference_provider_type="self-hosted",
         price_per_mtok_input_usd=None, price_per_mtok_output_usd=None, price_date=None, price_note=selfhost_note, role="candidate in both domains"),
    dict(id="Qwen/Qwen3.6-35B-A3B-FP8", display_name="Qwen3.6-35B-A3B (MoE, FP8)", vendor="Qwen (Alibaba)", weights="open", inference_provider_type="self-hosted",
         price_per_mtok_input_usd=None, price_per_mtok_output_usd=None, price_date=None, price_note=selfhost_note, role="candidate in both domains"),
    dict(id="qwen27b-rft", display_name="Qwen3.8-27B + LoRA RFT (our fine-tune)", vendor="Qwen (Alibaba) base, fine-tuned by us", weights="open",
         inference_provider_type="self-hosted", price_per_mtok_input_usd=None, price_per_mtok_output_usd=None, price_date=None, price_note=selfhost_note,
         role="fintech candidate", id_note="Local checkpoint name; not published."),
    dict(id="gpt-6.1-sol", display_name="GPT-6.1 Sol", vendor="OpenAI", weights="closed", inference_provider_type="vendor API",
         price_per_mtok_input_usd=2.0, price_per_mtok_output_usd=10.0, price_date=PD_API, price_note=api_note,
         role="alternative simulated customer (fintech robustness check); model behind the Codex coding agent in arm 1"),
    dict(id="gpt-4.1-mini-2025-04-14", display_name="gpt-4.1-mini", vendor="OpenAI", weights="closed", inference_provider_type="vendor API",
         price_per_mtok_input_usd=0.40, price_per_mtok_output_usd=1.60, price_date=PD_API, price_note=api_note,
         role="alternative simulated customer (retail-refunds pilot)"),
    dict(id="claude-sonnet-5-5", display_name="Claude Sonnet 5.5", vendor="Anthropic", weights="closed", inference_provider_type="vendor API",
         price_per_mtok_input_usd=2.0, price_per_mtok_output_usd=10.0, price_date=PD_API, price_note=api_note, role="model behind the Claude Code coding agent in arm 1"),
]
out["models"] = models
out["models_note"] = ("Self-hosted rows use inference_provider_type 'self-hosted', which is outside the spec's two values, because "
                      "they ran on our own vLLM servers. Models run only on commercial inference providers are withheld pending provider review.")

out["failures"] = [
    {"category": "needless handoff", "definition": "The agent handed the customer to a human (escalate_to_human) where the gold resolution has no handoff; usually after offering a transfer the customer accepted.",
     "counts": {"gpt-6-luna": 22, "qwen27b-bf16": 25, "qwen27b-fp8": 21}, "counts_scope": "Fintech hidden conversations GPT-5 resolved and the candidate did not (31, 42, 42), first failing decision (experiments/why_replay.md, generated from raw transcripts).",
     "example": "The agent offered to transfer the customer to a specialist, the customer accepted, and the correct resolution had no handoff."},
    {"category": "wrong refund arguments", "definition": "issue_refund called with arguments that differ from the gold (amount, transaction or reason).",
     "counts": {"gpt-6-luna": 1, "qwen27b-bf16": 9, "qwen27b-fp8": 10}, "counts_scope": "Same scope as above.",
     "example": "The agent issued a refund whose amount, transaction or reason differs from the correct one."},
    {"category": "identity never verified", "definition": "A required verify_identity call was never made before or instead of acting.",
     "counts": {"gpt-6-luna": 5, "qwen27b-bf16": 4, "qwen27b-fp8": 4}, "counts_scope": "Same scope as above.",
     "example": "The agent went ahead without the identity check the policy requires first."},
    {"category": "wrong escalation arguments", "definition": "escalate_to_human called with a reason that differs from the gold.",
     "counts": {"gpt-6-luna": 0, "qwen27b-bf16": 2, "qwen27b-fp8": 5}, "counts_scope": "Same scope as above.",
     "example": "The agent escalated with a different reason than the correct escalation."},
    {"category": "wrong dispute arguments", "definition": "open_dispute called with arguments that differ from the gold.",
     "counts": {"gpt-6-luna": 1, "qwen27b-bf16": 1, "qwen27b-fp8": 2}, "counts_scope": "Same scope as above.",
     "example": "The agent opened a dispute with a different reason than the scenario calls for."},
    {"category": "action not in the gold", "definition": "A write the gold does not contain at all (other than handoffs).",
     "counts": {"gpt-6-luna": 2, "qwen27b-bf16": 0, "qwen27b-fp8": 0}, "counts_scope": "issue_refund only, same scope as above.",
     "example": "The agent issued a refund the correct resolution does not contain."},
    {"category": "wrong card freeze arguments", "definition": "freeze_card called with arguments that differ from the gold.",
     "counts": {"gpt-6-luna": 0, "qwen27b-bf16": 1, "qwen27b-fp8": 0}, "counts_scope": "Same scope as above.",
     "example": "The agent froze the card with a different reason than the gold."},
    {"category": "tool calls never parsed (serving configuration)", "definition": "The endpoint's tool parser does not recognise the model's tool-call format, so no tool runs; conversations end normally with no errors.",
     "counts": {"qwen27b-hermes": 239}, "counts_scope": "Retail hidden, 240 conversations: 1 resolved, 1 infrastructure error (results.retail_hidden).",
     "example": "The agent says it has cancelled the order, but no cancellation was ever executed."},
    {"category": "infrastructure error (not graded)", "definition": "The conversation never got graded (here: a vLLM error).",
     "counts": {"qwen27b-hermes": 1}, "counts_scope": "Published hidden runs.",
     "example": "The request was refused with a rate-limit error before the conversation started."},
]
out["failures_note"] = ("Per-model counts for the first five categories cover only conversations the incumbent resolved and the candidate did not, "
                        "classified at the first failing decision. In the fix-loop diagnosis (all fintech hidden conversations) stock Qwen3.8-27B made 46 harmful "
                        "writes vs GPT-5's 15, 39 of them escalate_to_human with reason customer_request (experiments/fix_loop_fintech.md). "
                        "Unresolved and harmful-action counts for every run are in results.*.failures.")

R = out["results"]


def idx(cond, model):
    return [i for i, x in enumerate(R[cond]) if x["model"] == model][0]


out["headline_findings"] = [
    {"finding": "Next-step agreement approved 5 of the 8 regressed swaps and rejected both non-inferior swaps; full replay on 260 scenarios made no false safe and no false unsafe call, giving 5 correct verdicts and abstaining on the other 5 decidable swaps.",
     "numbers": ["results.verifier_tally[model=next-step agreement (5-pt threshold)].false_safe", "results.verifier_tally[model=next-step agreement (5-pt threshold)].false_unsafe",
                 "results.verifier_tally[model=replay-260].false_safe", "results.verifier_tally[model=replay-260].false_unsafe", "results.verifier_tally[model=replay-260].correct",
                 "results.verifier_tally[model=replay-260].not_enough_evidence"]},
    {"finding": "No next-step threshold avoids both errors: at 0-1 points it rejects both safe swaps, and from 2 points up it approves at least one regression.",
     "numbers": ["results.next_step_threshold_sweep[threshold_points=1].false_unsafe", "results.next_step_threshold_sweep[threshold_points=2].false_safe",
                 "results.next_step_threshold_sweep[threshold_points=5].false_safe"]},
    {"finding": "Imitation is not outcome: retail Qwen3.8-27B FP8 matched the incumbent's next tool call on 440 of 475 steps yet resolved 9.8 points fewer hidden conversations.",
     "numbers": ["replays_and_step_checks[domain=retail,candidate=qwen27b-fp8].next_step.agreement", "results.retail_hidden[model=qwen27b-fp8].delta_vs_incumbent",
                 "results.retail_hidden[model=qwen27b-fp8].delta_vs_incumbent_ci95"]},
    {"finding": "A three-line policy clarification turned the regressed self-hosted Qwen3.8-27B into a non-inferior bank agent on the hidden set and on 200 never-inspected pool scenarios, while tool guardrails alone changed nothing.",
     "numbers": ["results.fintech_hidden[model=qwen27b-bf16].delta_vs_incumbent", "results.fintech_hidden[model=qwen27b-guards].delta_vs_incumbent",
                 "results.fintech_hidden[model=qwen27b-fixed].delta_vs_incumbent_ci95", "results.fintech_pool_fix_confirmation[model=qwen27b-fixed].delta_vs_incumbent_ci95"]},
    {"finding": "The same weights behind vLLM's generic hermes tool parser resolved 1 of 240 retail conversations, with no errors raised: endpoint configuration is a swap risk of its own.",
     "numbers": ["results.retail_hidden[model=qwen27b-hermes].correct", "results.retail_hidden[model=qwen27b-hermes].n", "results.retail_hidden[model=qwen27b-hermes].accuracy"]},
    {"finding": "Fine-tuning Qwen3.8-27B on its own successful bank conversations did not change success or harm; only output tokens fell.",
     "numbers": ["results.fintech_hidden[model=qwen27b-rft].delta_vs_incumbent", "results.fintech_hidden[model=qwen27b-bf16].delta_vs_incumbent",
                 "results.fintech_hidden[model=qwen27b-rft].mean_output_tokens_per_case", "results.fintech_hidden[model=qwen27b-bf16].mean_output_tokens_per_case"]},
]

out["limitations"] = [
    "Simulated customers only: Claude Haiku 5.5 plays every customer. A stronger simulator (GPT-6.1 Sol) moved fintech success rates up 2-5 points but barely moved the candidate-vs-incumbent gaps; a weaker one (gpt-4.1-mini) shifted a retail verdict by 17.5 points. Verdicts were never compared with real customers.",
    "Ground truth by construction assumes a faithful customer; script breaks by the simulator corrupt the truth itself.",
    "Scenario quality was checked by a Claude reviewer on 50 hidden scenarios, not by a human. One retail kind (cancel an already-delivered order, 50 of 240 hidden retail scenarios) penalizes helpful agents; it was kept in the released numbers.",
    "Scale: two domains, one incumbent per domain, 13 scored candidate swaps (10 with decidable truth: 8 regressed, 2 non-inferior). Error rates of the checks have wide uncertainty (e.g. 0 of 8 vs 5 of 8 false safes); the planned exact intervals and paired tests were not run.",
    "Truth is itself estimated from 240 scenarios x 2; three candidates have AMBIGUOUS truth and are not scored. Pooled over 500 scenarios, GPT-5 mini also raises harmful actions (+0.026 per conversation), so its NON-INFERIOR label holds for hidden-set success only (experiments/sample_size.md).",
    "The replay checks and the truth use the same simulator, harness and grader (not independent); an independent-simulator truth was planned but not run.",
    "The v1 hidden sets were generated from seeds in the private research repository's history, so they guard against agents peeking during a run, not against deliberate gaming.",
    "Costs: API costs use list prices pinned on 2026-10-13/15, not invoices; the simulated customer is excluded; self-hosted costs are GPU time at one concurrency level, without engineering or operations.",
    "Self-hosted FP8 and MoE fintech runs combine one full trial with a partial second trial cut short by a restart (445 and 481 conversations).",
    "Coding-agent arm 1: 13 runs only, two tasks, Harbor sandboxes; arm 2 (agent plus toolkit) was built but not run.",
    "Inferred mocks were tested on two domains with simple stateful CRUD tools on synthetic data, and scored against hand-written tools that are themselves mocks.",
    "Next-step agreement verdicts depend on a threshold; one 'correct' verdict (qwen27b-rft, 84.9% vs an 85.0% cut-off) rests on a 0.1-point margin.",
    "Prior work already establishes the mechanisms (compounding per-step errors, simulator effects, provider variance); the contribution is measuring swap checks against ground-truth outcomes.",
]

out["public_safety"] = []  # set by publish.py
