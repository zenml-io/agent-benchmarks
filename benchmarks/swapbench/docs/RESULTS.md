# SwapBench: first results (Oct 13–14, 2026)

**One-line summary.** Coding agents left alone did not ship unsafe swaps: 0 false-safe calls in 13
graded runs. They also approved a genuinely safe 87%-cheaper swap. The cheap model still fell into
the trap we set, regressing on hidden traffic while tying on the visible traces, but no agent
picked it. The verdict depends on two parts of the replay setup we found tonight:
- **who plays the customer** (+17.5 pts swing);
- **how the endpoint is configured** (−77 pts from a wrong tool parser).

Those two, not the agent's judgement, are where a swap "referee" adds value.

## 1. The riskiest assumption: do agents claim SAFE when it isn't?

**Setup.**
- **Agents:** Codex (GPT-6.1 Sol) and Claude Code (Sonnet 5.5), in Harbor sandboxes on Modal.
- **Isolation:** the network was limited to the model APIs while the agent ran, and the hidden scenarios were stripped from disk.
- **The job:** cut the cost of a GPT-5 support agent by at least 50%, then declare SAFE, UNSAFE or INSUFFICIENT_EVIDENCE.
- **Grading:** on hidden scenarios (`experiments/arm1_retail_refunds.md`, `experiments/graded_retail_composite.jsonl`).

| Task | Runs | Declared | Hidden-set truth | Outcome |
|---|---|---|---|---|
| retail-refunds (tau2 retail; 74 visible, 40×3 hidden) | 8 | 6 UNSAFE, 2 INSUFFICIENT | 5 regressed, 2 ambiguous, 1 no-swap | 5 correct rejections, 3 no decision; **0 false-safe** |
| retail-composite (generated multi-request; 60 visible, 240 hidden) | 5 | 5 SAFE | Haiku: not worse (+0.4 [−2.9, +3.8]); gpt-5-mini + prompt suffix: not worse (+0.0 [−4.2, +5.0]); gpt-5-mini + settings: ambiguous (−2.5 [−8.3, +3.3]) | **4 correct SAFE** (82–87% cheaper), 1 SAFE on ambiguous; **0 false-safe** |

**What we learned.**
1. **Pre-registered verdict: the assumption failed.** 0 false-safe in 13 runs. Agents replayed every
   visible scenario, compared outcomes scenario by scenario, gave intervals (6 of 7 covered the
   hidden truth on task 1), audited database writes by hand, and abstained when unsure.
2. **They don't over-reject either.** Where a swap was truly safe (Haiku on task 2, 87% cheaper),
   all three Claude Code runs approved it. So did one Codex run with a prompt-tuned gpt-5-mini
   (82% cheaper).
3. **The trap existed and was dodged.**
   - On task 2, GPT-6 Luna tied the incumbent on the visible traces (+0.0) but is −6.7 [−11.2, −2.1] on the hidden set, at 98% cheaper. No agent shipped it.
   - The two Codex runs shipped gpt-5-mini configs while expecting +8 to +10 points. One holds up
     (+0.0 [−4.2, +5.0] with Codex's prompt suffix); the other is unproven (−2.5 [−8.3, +3.3]).
   - Their optimism came from the visible sample: GPT-5 scored 88% there but 95% on the hidden set.
   - On task 1 the visible sample erred the other way, making candidates look worse.
4. **Why the bias.** Comparing fresh replays with a single recorded incumbent trace per scenario
   inherits that one sample's luck. A statistical gate alone doesn't fix this. More scenarios, or
   replaying the incumbent alongside, does.

## 2. Who plays the customer flips the verdict (`experiments/simulator.md`)

Same 40 scenarios × 3 trials; only the simulated customer changes:
- With Haiku as the customer: Luna −1.7 vs Haiku, which looks safe.
- With gpt-4.1-mini as the customer: −19.2 [−31.7, −6.7], clearly worse.

The difference is **+17.5 [+4.2, +30.8] pts**. Cause: gpt-4.1-mini breaks its script (accepts
alternatives it was told to refuse), Luna offers alternatives more readily, and ground truth by
construction assumes a faithful customer. **A replay harness needs a validated customer simulator**,
or its verdicts are wrong in either direction.

## 3. Open-weight models and the endpoint (`experiments/open_models_retail.md`)

On the hidden set of task 1, against GPT-5's 83.3% and with vLLM on one H100:

| Candidate | Success rate | Gap vs GPT-5 [95% CI] | Cost cut |
|---|---|---|---|
| Qwen3.8-27B, BF16 | 81.7% | −1.7 [−10, +6.7] | 88% |
| Qwen3.8-27B, FP8 | 82.5% | −0.8 | 90% |
| Qwen MoE (3B active) | 78.3% | −5.0, on the margin | 94% |
| Qwen3.8-27B with vLLM's generic `hermes` tool parser | **5%** | −77 | 89% |

The `hermes` row uses the same weights. Its tool calls are never parsed, there are no errors, and
every conversation ends normally. The endpoint config is a first-class swap risk.

## 4. What this means for the product thesis

- **"Agents alone falsely declare swaps safe"** is **not** supported. Don't lead with it.
- **Supported, and what a referee would sell:**
  1. **Evidence size.** 40–74 conversations can't separate "fine" from "5 points worse"; agents
     correctly abstain or guess. We needed 240 fresh scenarios to call Haiku safe and Luna regressed.
     A generator of fresh scenarios with ground truth by construction is the asset
     (`swapbench/gen_retail.py`).
  2. **A validated replay harness.** The customer simulator's fidelity swings verdicts by about 17 pts.
  3. **Endpoint verification.** The same weights behind the wrong parser drop from 82% to 5%,
     silently.
- **Benchmark design lessons.**
  - Templated single-request scenarios are too easy (98–100% for every model). Difficulty comes
    from multi-request conversations.
  - Hidden sets need 200+ scenarios.
  - Report simulator fidelity next to every verdict.

## 5. Not done, and the next step

- **Arm 2 (agent + toolkit) was built but not run.** It's the `sb` CLI: paired replay, CI gate,
  extra scenario pool. Running it needs incumbent replays, which were
  out of scope for this round.
  - Given section 1, the useful arm-2 question is **realized savings and calibration**, not false-safe.
  - Best test task: one where the right answer is SAFE but takes more than 60 scenarios to show
    (like gpt-5-mini here).
  - Estimate: about $60 OpenAI + $30 Anthropic for 4+4 runs.
- **Harder and subtler regressions.** Tail-only failures (one request type breaking), and swaps
  that regress only on harmful writes.
- **Real customer turns** to calibrate the simulator.
