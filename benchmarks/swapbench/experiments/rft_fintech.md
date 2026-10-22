# Fine-tuning Qwen on its own successful fintech conversations (Oct 14)

**What we trained.** Rejection-sampling fine-tuning (RFT):
- **Data:** Qwen3.8-27B's own fintech conversations that reached the correct end state with no harmful write. They come from scenarios disjoint from the eval sets. That gives 1,134 examples, one per customer turn, with reasoning kept.
- **Method:** LoRA r=32 on attention and MLP projections, 1 epoch, lr 1e-4, on one H200. This is `rft/train_lora.py`.
- **Loss:** flat around 0.35 throughout, as expected when a model trains on its own outputs.

**How we evaluated it.** Same protocol as stock Qwen:
- the next-step check against GPT-5's train traces;
- 60 visible scenarios × 1;
- 240 hidden scenarios × 2;
- 200 pool scenarios × 1;
- Haiku 5.5 customer, one H100 per split.

## Against GPT-5 (incumbent)


| candidate | truth: Δ on 240 hidden [95% CI] | truth | next-step tool agreement | nextstep verdict | replay-60 Δ [CI] | replay-60 verdict | replay-260 Δ [CI] | replay-260 verdict |
|---|---|---|---|---|---|---|---|---|
| qwen27b | -5.6 [-8.8, -2.5] | REGRESSED | 85.7% | SAFE | -5.0 [-13.3, +3.3] (n=60) | INSUFFICIENT_EVIDENCE | -5.8 [-9.6, -1.9] (n=260) | UNSAFE |
| qwen27b-rft | -4.4 [-7.3, -1.7] | REGRESSED | 84.9% | UNSAFE | -3.3 [-11.7, +5.0] (n=60) | INSUFFICIENT_EVIDENCE | -3.5 [-7.7, +0.8] (n=260) | INSUFFICIENT_EVIDENCE |

| verifier | qwen27b | qwen27b-rft |
|---|---|---|
| nextstep | FALSE SAFE | correct |
| replay-60 | abstain | abstain |
| replay-260 | correct | abstain |

## Tuned vs stock Qwen (paired on the 240 hidden scenarios, 2 trials each)

| metric | stock | tuned | Δ [95% CI] |
|---|---|---|---|
| task success | 88.5% | 89.8% | +1.3 [−1.9, +4.4] |
| harmful writes / episode | 0.096 | 0.092 | −0.004 [−0.035, +0.027] |
| agent calls / episode | 9.42 | 9.40 | −0.02 [−0.14, +0.09] |
| output tokens / episode | 2,341 | 2,047 | **−294 [−381, −211]** (−13%) |

## Reading

- **One epoch of RFT on ~1.1k self-generated examples did not measurably change outcomes.**
  - Success +1.3 points, CI includes 0. Harm unchanged.
  - Both models are still clearly behind GPT-5, mainly on harmful writes: 0.09 vs 0.03 per episode.
  - The one robust effect is 13% fewer output tokens, i.e. shorter reasoning: cheaper and faster for the same outcome.
- **Next-step agreement also barely moved:** 85.7% → 84.9%.
  - The verdict flipped from SAFE to UNSAFE only because 84.9% falls just under the 85.0% threshold.
  - That "correct" call rests on a 0.1-point margin of a metric that didn't change. It shows how brittle the threshold is, not that the check works.
- **The hypothesis "tuning raises the proxy but not the outcome" was not tested by this run:** neither moved. A real test needs a training signal strong enough to move something, for example:
  - more data or epochs;
  - targeting the failure clusters (needless escalations, harmful writes);
  - RL with the simulator and the end-state reward.
- **Spend:** about $6.5 for the H200 training run, $1 for the merge, and $6.4 for the 4-GPU evaluation.
