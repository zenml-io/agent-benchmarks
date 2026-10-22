# Can "send us your traces" replace hand-building the customer's tools? (Oct 14)

**One line:** yes, for these two domains. Mocks inferred by an agent from **25–50 recorded conversations** reproduced
98–100% of tool outputs on unseen conversations and every swap verdict. The part traces cannot settle is the *grading
rule*, meaning which state changes count as correct. That needs a short sign-off from the customer. If the grading rule
is fixed, onboarding is a product. If it is left to inference, verdicts stay right but effect sizes can drift.

## Setup

**Input: only what an agent's own traces contain.** Built with `scripts/mockgen_package.py`:
- `tools.json`: the tool schemas exactly as the agent saw them in its prompt;
- `policy.md`: the agent's policy;
- `data.json`: the data snapshot each conversation starts from, without internal state;
- `traces.jsonl`: N recorded incumbent conversations (GPT-5 for fintech, Haiku 5.5 for retail), as nested prefixes
  of one shuffle, with N = 25, 50, 100, 260.

The agent got no tool source code, no tool documentation beyond the prompt schemas, and no grader.

**Builder.** A separate Claude agent per package, with no access to the repo, tau2 or the web, was asked to:
- infer a state store, each tool's behaviour, state changes and errors;
- use recorded outputs for exact matches, and generalize the rest from inferred rules;
- flag every guess at run time (`flags`, `GUESSES`);
- define `state()` for grading;
- write `NOTES.md`.

Each mock, with its notes, is in this folder (`fintech_N/`, `retail_N/`).

**Offline scoring (`scripts/mock_fidelity.py`).**
- **Data:** every hidden-set conversation of 6 fintech runs (GPT-5, GPT-5 mini, GPT-6 Luna, GPT-5.4 nano, Qwen BF16, Qwen
  FP8; 2,845 conversations) and 4 retail runs (Haiku 5.5, Qwen FP8, Qwen MoE, Qwen no-thinking; 1,920 conversations).
  None of these conversations were given to the mock builder, and most come from other models, so they take paths the
  incumbent never took.
- **Per-call check:** replay each conversation's tool calls on the hand-written tools and on the inferred mock, and
  compare each call's output and error.
- **Grading:** grade both backends the way tau2 does: replay the state-changing calls, and compare the end state with
  the scenario's gold actions on the same backend.
- **Per-call agreement is exact evidence.** Where every call agrees, the conversation would have unfolded identically
  on the inferred mock.

**Live validation.** We ran the incumbent and a Qwen candidate on the 240 hidden scenarios × 2 against the 260-trace mocks,
served with the agent's exact tool interface (`swapbench/genmock.py`, domains `fintech_gen` / `retail_gen`). The Haiku
customer was the same as before, and nothing else changed.

## Results

### How many traces until the verdicts stop changing

| domain | traces given | conversations scored | tool calls agreeing | conversations with every call agreeing | final grade agrees | swap verdicts unchanged |
|---|---|---|---|---|---|---|
| fintech | 25 | 2,845 | 98.4% | 94.6% | 95.0% | 5/5 |
| fintech | 50 | 2,845 | 98.4% | 94.6% | 99.3% | 5/5 |
| fintech | 100 | 2,845 | 98.4% | 94.6% | 99.3% | 5/5 |
| fintech | 260 | 2,845 | 99.9% | 99.7% | 97.2% | 5/5 |
| retail | 25 | 1,920 | 99.9% | 99.5% | 100.0% | 3/3 |
| retail | 50 | 1,920 | 100.0% | 100.0% | 100.0% | 3/3 |
| retail | 100 | 1,920 | 100.0% | 100.0% | 100.0% | 3/3 |
| retail | 260 | 1,920 | 100.0% | 100.0% | 100.0% | 3/3 |

**Extra condition: 260 traces plus full tool documentation.** This was an earlier mock, given the tools' docstrings
including their return descriptions. It reached 99.8–100% tool-call agreement, 98.8–100% grade agreement and 5/5
verdicts unchanged (Qwen BF16 −6.0, FP8 −6.5). That is no better than traces alone at 50+ conversations, so
documentation beyond the prompt schemas adds little here.

Verdicts never changed. Effect sizes (Δ success vs incumbent, hidden set):

| candidate | hand-written | 25 traces | 50 | 100 | 260 |
|---|---|---|---|---|---|
| fintech Qwen BF16 | −5.6 | **−12.9** | −5.6 | −5.6 | −5.8 |
| fintech Qwen FP8 | −6.0 | **−12.9** | −6.5 | −6.5 | −6.2 |
| fintech GPT-6 Luna | −2.5 | −3.3 | −3.1 | −3.1 | −3.3 |
| fintech GPT-5 mini | +0.2 | −1.0 | −1.0 | −0.8 | −0.8 |
| fintech GPT-5.4 nano | −37.5 | −37.5 | −38.5 | −38.5 | −36.7 |
| retail Qwen FP8 | −9.8 | −9.8 | −9.8 | −9.8 | −9.8 |
| retail Qwen MoE | −0.6 | −0.6 | −0.6 | −0.6 | −0.6 |
| retail Qwen no-thinking | −2.5 | −2.5 | −2.5 | −2.5 | −2.5 |

**Answer to "how many traces":**
- **Retail:** 25 conversations were enough.
- **Fintech:** verdicts were right at 25, but effect sizes settled at 50.
- **At 25 traces in fintech,** the agent chose to count failed identity checks in the graded state. That doubled
  Qwen's measured gap: Qwen retries verification more often than GPT-5. It is a grading choice, not a tool error.

### Live runs on the inferred mocks (260 traces)

| domain | backend | incumbent | candidate | Δ [95% CI] | truth |
|---|---|---|---|---|---|
| fintech | hand-written | GPT-5 94.2% | Qwen BF16 88.5% | −5.6 [−8.8, −2.5] | REGRESSED |
| fintech | inferred | GPT-5 93.8% | Qwen BF16 87.1% | −6.7 [−10.2, −3.3] | REGRESSED |
| retail | hand-written | Haiku 95.4% | Qwen FP8 85.6% | −9.8 [−13.8, −6.0] | REGRESSED |
| retail | inferred | Haiku 95.8% | Qwen FP8 85.4% | −10.4 [−13.8, −7.1] | REGRESSED |

There were no infrastructure errors in any of the 1,920 live conversations. How often did the same model pass or fail
the same scenario on both backends, compared with two runs on the same backend?

| | two runs, same backend | hand-written vs inferred |
|---|---|---|
| fintech (GPT-5) | 91.7% | 88.3% |
| retail (Haiku) | 92.5% | 92.5% |

The inferred backend adds little or no disagreement beyond run-to-run noise.

## What could not be inferred from traces

**Tool behaviour that was never observed.**
- **Error responses.** None of the incumbent's traces contains an errored call, so every error condition and message is
  a guess. In scoring, the only fintech output mismatch below 260 traces is the response to a *failed identity check*:
  the mock added `"customer_id": null`. The 260-trace package contained failed checks, and that mock got it right.
- **Tools the incumbent never called** (retail at small N: `modify_pending_order_payment`, `modify_user_address`,
  `get_item_details` and others). Their outputs were guessed and flagged. They rarely matter for grading.
- **Effects never read back:** gift-card balance changes, card status after a freeze, whether a refund changes the
  balance. These are flagged as guesses; flags fired on 3–19% of calls (2.8–19.4% by mock).

**The grading rule.** Every grading disagreement we traced was a choice about what the end state should contain, not a
wrong tool output:
- Count failed identity checks (fintech, 25 traces).
- Record "escalated after two failed checks". Our own gold for those scenarios lists only the escalation, so they
  can never match (fintech, 260 traces).
- Do not record identity verification at all. Our hand-written tools do, so a conversation with no actions and no
  verification passes on the mock and fails on ours (fintech, 260 traces).
- Count transfers to a human (all retail mocks). tau2 itself skips transfers when grading, so live results were
  unaffected; see the scorer note below.
- Treat independent actions as unordered. Our hand-written fintech tools record order, which fails 4 of 110 failed
  conversations purely for handling two requests in a different order.

Each of these is a policy question for the customer: does a needless transfer count, does a retried identity check
count, does the order of independent actions matter? Traces cannot settle them, because the incumbent rarely does the
wrong thing. Several of the inferred choices are arguably closer to the written policy than our hand-written ones.

## What this means for onboarding

- **"Send us your traces" works for the tool layer.** About 50 conversations of the incumbent were enough here, plus the
  tool schemas and policy already in those traces, and a data snapshot to seed scenarios.
- **Add a grading checklist the customer confirms**, of 5–10 yes/no questions generated from the policy and the mock's
  `state()` (transfers, retries, ordering, verification). That removes the effect-size drift seen at 25 traces.
- **The scenario world still needs data.** We gave the snapshot. A customer would provide a sanitized export, or the
  scenario generator would synthesize records in the inferred schema; we did not test the latter.
- **Caveats:**
  - Two domains with simple stateful CRUD tools (7 and 15 tools), on synthetic data.
  - Real APIs have rate limits, pagination, side effects across systems and undocumented errors that a few hundred
    traces may never show.
  - The inferred mocks were scored against hand-written tools that are themselves mocks.

## Scorer note

The first offline scoring replayed *every* call when grading, so the retail mocks' "transferred to human" flag made
Qwen FP8 look 18.5 points worse instead of 9.8, and flipped one verdict. tau2 skips tools marked
`mutates_state=False`, such as `transfer_to_human_agents`, when it grades. The scorer now does the same, and live runs
confirm it (retail −10.4 live vs −9.8 hand-written). All numbers above use the corrected scorer.

**Cost.** About $49 of API for the live runs (GPT-5 $35.50, Haiku about $13). GPU for the Qwen live runs was about $8.
The mock-building agents ran in this session.
