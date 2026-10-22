# Closing the gap: guardrails and a policy clarification for Qwen (fintech, Oct 14)

**Setup.** The incumbent is GPT-5; the candidate is stock Qwen3.8-27B (BF16, vLLM, one H100). The customer is Haiku 5.5. Truth uses the paired cluster bootstrap with a 5-point margin.

**Diagnosis** (`harm_kinds`, on the hidden set). Stock Qwen made 46 harmful writes in 480 episodes. GPT-5 made 15.
- 39 are `escalate_to_human` with reason `customer_request` where the scenario calls for no escalation. In 33 of them Qwen mentioned a specialist first and the customer accepted. GPT-5 rarely offers.
- 6 are writes before identity verification.
- None are wrong amounts, ineligible fees or out-of-window disputes.

**Fixes.** Both are committed in `swapbench/fintech/domain.py` and `policy_addendum.md`.
1. **Hard guardrails in the tools** (`SWAPBENCH_GUARDS=1`):
   - identity required before acting;
   - fee eligibility, the $40 cap and one refund per 365 days;
   - the duplicate-charge definition and the $500 limit;
   - the dispute window, posted purchases only, and freeze-before-unauthorized;
   - escalate once.

   All 500 gold action sequences pass them.
2. **A three-line policy clarification** (`SWAPBENCH_POLICY_ADDENDUM`):
   - don't offer a human;
   - "not eligible" is a complete answer;
   - `out_of_scope` is only for unlisted services.

## Hidden set (240 × 2): where the failures were diagnosed

| arm | success | harmful writes / episode | Δ vs GPT-5 [95% CI] | harm Δ vs GPT-5 | verdict |
|---|---|---|---|---|---|
| GPT-5 | 94.2% | 0.031 | | | |
| Qwen stock | 88.5% | 0.096 | −5.6 [−8.8, −2.5] | +0.065 [+0.035, +0.096] | REGRESSED |
| Qwen + guards | 88.8% | 0.098 | −5.4 [−8.8, −2.3] | +0.067 [+0.037, +0.098] | REGRESSED |
| Qwen + guards + clarification | 92.9% | 0.046 | −1.2 [−4.0, +1.5] | +0.015 [−0.008, +0.040] | NON-INFERIOR |

## Pool (200 scenarios, never inspected): confirmation

| arm | success | harmful writes / episode | Δ vs GPT-5 [95% CI] | harm Δ vs GPT-5 | verdict |
|---|---|---|---|---|---|
| GPT-5 (1 trial) | 93.5% | 0.035 | | | |
| Qwen stock (1 trial) | 87.5% | 0.100 | −6.0 [−10.5, −1.5] | +0.065 [+0.025, +0.110] | REGRESSED |
| Qwen + guards + clarification (2 trials) | 93.0% | 0.033 | −0.5 [−4.2, +3.5] | −0.003 [−0.035, +0.028] | NON-INFERIOR |

On the pool, the fixed model beats stock by +5.5 [+1.0, +10.2] points of success and −0.068 [−0.115, −0.022] harmful writes per episode.

## Reading

- **Guardrails alone changed nothing.** They blocked 12 calls in 480 episodes, but Qwen's failures were behavioral (offering escalation), not rule-breaking money moves.
- **The clarification fixed the behavior,** and the fix held on scenarios not used to find it. The candidate goes from REGRESSED to NON-INFERIOR against GPT-5.
- **Cost per conversation:** GPT-5 is $0.072 at list API prices, the mean over the hidden set. Qwen on one H100 at 12 concurrent conversations is about $0.009 (≈ $2.1 of GPU per 240 conversations, including startup). That is about 88% cheaper. It assumes steady utilization and leaves out engineering and ops cost.
- **Caveats:**
  - One domain, one model pair, one fix.
  - The fix was found by hand from the failure breakdown. Automating that step is the product question.
  - The customers are simulated (Haiku 5.5); see `simulator_fintech.md` for robustness.
  - GPT-5 was not re-run with the clarification; it might also improve.
