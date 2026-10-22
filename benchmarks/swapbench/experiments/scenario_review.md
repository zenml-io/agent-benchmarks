# Checking 50 generated scenarios (Oct 14)

## How it was checked

**Sample.** 50 scenarios drawn at random (seed 42) from the 240 hidden scenarios: 30 fintech and 20 retail. Each was exported as a self-contained packet:
- the simulated customer's instructions;
- the gold actions;
- the policy;
- the customer's record, accounts, cards and transactions (fintech), or the user, orders and products (retail).

**Reviewer.** A separate Claude agent, not a human. It had no access to the generator or grader code and followed a written protocol. For each packet:
1. **Derive.** Write down from the policy alone the actions a correct agent must take, before looking at the gold.
2. **Facts.** Check every fact the customer will state against the data.
3. **Compare.** Compare the derivation with the gold actions.
4. **Ambiguity.** Look for an alternative policy-compliant path that ends in a different state.
5. **Drivability.** Check that the customer can supply everything the agent will ask for.
6. **Verdict.** PASS, MINOR (wording; end state unaffected) or FAIL (gold wrong, ambiguous, or not drivable).

The full protocol as applied, every verdict and the per-packet derivations are in `scenario_review/REVIEW.md` and `scenario_review/review.jsonl`. I verified the FAIL pattern myself against the data and the generator; see below.

## Result

| domain | PASS | MINOR | FAIL |
|---|---|---|---|
| fintech | 26 | 4 | 0 |
| retail | 13 | 3 | 4 |
| all | 39 | 7 | 4 |

- **Gold actions:** all 50 matched the reviewer's policy derivation (ids, amounts, reasons, order).
- **The 4 FAILs** share one retail generator rule, `cancel_refuse`. The customer asks to cancel an order that is already *delivered*, and the gold is "no action". The policy allows returns of delivered orders, so a helpful agent may offer one, the customer may accept, and the end state then differs from the gold. This rule penalizes good agents.
- **MINOR:** template wording, such as "the order never arrived" for a hotel charge. In every case the correct end state is unaffected (no action either way). In the retail cancellation requests, the customer names only some of the order's items.
- **Escalation summaries:** the reviewer suspected that their free text might be graded. It isn't: grading compares end state, and the summary is not stored. Only `reason` and `identity_verified` are.

## How much the flaw affects results

The rule hit 50 of the 240 hidden retail scenarios (21%): 17 of 60 visible, 47 of 200 pool. Recomputing the retail truth without them:

| candidate | Δ vs Haiku, all 240 | truth | Δ vs Haiku, 190 clean | truth |
|---|---|---|---|---|
| Haiku re-run | −2.1 [−5.4, +1.2] | AMBIGUOUS | −1.6 [−5.3, +1.8] | AMBIGUOUS |
| Qwen FP8 | −9.8 [−13.8, −6.0] | REGRESSED | −8.4 [−12.6, −4.2] | REGRESSED |
| Qwen MoE | −0.6 [−3.3, +2.1] | NON-INFERIOR | −0.8 [−3.9, +2.4] | NON-INFERIOR |
| Qwen no-thinking | −2.5 [−5.4, +0.2] | AMBIGUOUS | −1.8 [−5.0, +1.3] | AMBIGUOUS |
| Qwen hermes parser | −95.0 | REGRESSED | −95.3 | REGRESSED |

- **No truth label changes.** Qwen FP8 does worst on the flawed scenarios (81% vs 87% on clean ones), so about 1.4 points of its −9.8 come from this flaw. It is still clearly regressed without them.
- **Fix:** `gen_retail.py` now prefers *processed* orders for this scenario kind. The customer declines any return or exchange offer, and cancellation requests name every item. The released hidden set is unchanged, so published numbers stay comparable; the issue is documented here.
