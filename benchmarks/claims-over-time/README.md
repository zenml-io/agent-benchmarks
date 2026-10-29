# Claims over time: improving an appeals agent batch by batch

## Question

When a claims-review agent meets new cases in batches, with only a few outcomes coming back each time, how much does each round of improvement help, and does an improver that works through recorded traces and replays (the ZenML Pro agent with Kitaru) do better, or more cheaply, than a strong coding agent working from trace files (Codex)?

## Status

**Two complete runs of all eight rounds.**

- **Second run (2026-10-28 to 2026-10-29), with held-out approval.** The ZenML Pro agent's line ended ahead of both others: over all 800 appeals, 3.3 points of balanced accuracy above Codex's (paired 95% CI +0.9 to +5.8) and 4.0 above the line left alone (+1.1 to +6.9). Codex's line ended level with the line left alone (+0.7, -2.5 to +4.0). Most of the gap opened after the switch to the open model, where the ZenML Pro agent raised the limits that left appeals undecided and Codex did not. That is the comparison a team would meet: Codex asked to improve the agent with no further guidance, against the ZenML Pro agent with Kitaru and our prompting. One piece of that prompting sat in the benchmark, not the product: the ZenML Pro arm's task line asked it to count how every recorded session ended before choosing what to study, and named the version that recorded each batch. A customer would not type that line. The product's own skill has the same rule, which the agent skipped in the mini rounds (section "Second run").
- **First run (2026-10-27 to 2026-10-28), approval on the revealed appeals.** No improver beat the agent that was left alone by a margin this design can detect (section "First run").

Spend on the second run: $45.61 for the open model's server (Modal's bill) and about $31 of OpenAI usage by the frameworks' estimates: $13.42 for the batches on `gpt-6.1-sol` (rounds 1 to 3), $10.56 for approvals, $5.68 for Codex's reruns and $1.26 for both improvers; the ZenML Pro agent's Kitaru experiments are not included. It took 11 hours 9 minutes from the first batch to the last audit, including one restarted ZenML Pro trial. Spend on the first run: about $87, of which $54.53 for the open model's server (Modal's bill) and about $32 of OpenAI usage: the claims agent on `gpt-6.1-sol` in rounds 1 to 3 ($11.91 for the batches, $9.04 for approvals, $4.38 for Codex's reruns and $5.66 for the ZenML Pro agent's Kitaru experiments) and $1.26 for both improvers over all rounds and retries. Building and checking the harness on 2026-10-27 cost about $13 more (case-file extraction $3.19 on Modal's bill; classifier training about $1.60 of GPU time; calibration runs about $2.50; smoke tests and mini rounds about $1.50; interruption tests about $4.05, of which $2.74 on Modal's bill). OpenAI costs are the frameworks' own estimates, not checked against the bill.

## Design

- **Cases.** California Independent Medical Review appeals from 2025 and 2026 ([CalHHS open data](https://data.chhs.ca.gov/dataset/independent-medical-review-imr-determinations-trend)): a health plan denied a treatment, the patient appealed, an independent reviewer upheld or overturned the denial. The agent reads a facts-only case file and a library of 19,374 earlier decisions (2016-2023), and decides. It is graded by exact match against the real ruling.
- **Stream.** 3,131 usable appeals in filing order, cut into 9 equal windows. One window gives the calibration batch (batch 0), the others give batches 1 to 8. Each batch is 100 appeals drawn at random from its window; 20 per batch are "revealed", meaning their ruling becomes available to the improvers after the batch is scored. `data/stream.jsonl` lists IDs, batches and revealed flags. Rulings stay out of the repository until the experiment ends.
- **Lines.** `left_alone` (the starting agent, never changed), `codex` and `pro` (each improved once per round). Each round: every line decides the new batch, the batch is scored, its outcomes are revealed, each improver proposes one change in a sealed Harbor trial, and a fixed rule ships the change only if it scores at least as well as the current version (the next two items).
- **Approval rule of the first run, changed after its round 1.** The candidate and the current version each run three times on every revealed appeal so far, and the candidate ships if its mean balanced accuracy is at least the current version's. The rule as first written used one run each. In round 1, with 20 revealed appeals of which 4 were upheld, one upheld appeal is worth 12.5 points of balanced accuracy, and Codex's candidate scored 0.969 in its own rerun and 0.719 at approval minutes later. Round 1's approval was redone under the three-run rule and gave the same decision (not shipped: 0.802 against 0.823); the original decision is kept in the round's records. Improvers see the three-run rule from round 2.
- **Approval rule of the second run: held-out appeals.** The rule above scores a candidate on the same revealed appeals the improver studied, so a change fitted to those appeals passes it. `round.py` now defaults to `--approval-on held-out`: each batch also gets 20 unrevealed appeals (4 in a mini round), drawn with a fixed seed in the batch's uphold/overturn proportion, and approval runs on every held-out set so far. Their rulings stay on the host, so neither improver can fit to them. The decision also reports, for each version, the mean number of appeals wrongly denied, wrongly approved and left undecided. `--approval-on revealed` reproduces the rule of the first run.
- **Model switch.** Rounds 1 to 3 run the claims agent on `gpt-6.1-sol`. Before batch 4, every line switches to Qwen3.8-27B served by vLLM, the cheaper open model the original agent ran on.
- **Fairness rules.** Both improvers run on `gpt-6-luna`, get the same instructions except one line (`harness/improver_instructions.md`), the same revealed rulings, the same budget (3 reruns on the revealed appeals, 45 minutes; Codex reruns with a `claims-rerun` tool, the ZenML Pro agent only through Kitaru experiments, and any other run of the agent found in an improver's command log counts as over budget) and the same network (the model API, and for `pro` the Kitaru workspace). In the second run the ZenML Pro agent's line also asks it to count how every recorded session ended (a decision, an error, or a stop at a token, request or time limit) before choosing sessions, and names the agent version that recorded each batch; Codex's line does not have that sentence. The ZenML Pro agent's built-in instructions also say to retry a network error up to three times. An improver can never read the ruling of an unrevealed appeal, and no score of an unrevealed appeal is written anywhere an improver can read.

## Results

### Second run (2026-10-28 to 2026-10-29)

Held-out approval, the ZenML Pro agent's longer instruction line (section "Design", "Fairness rules"), and the same cases, batches, revealed appeals and models as the first run. Rows in `work/runs/`, round records in `work/rounds/`.

#### Over time (batches 1 to 8, 100 appeals each)

Balanced accuracy of each line on each new batch, decided by the version that was current before the batch's outcomes were revealed. Batches 1 to 3 ran on `gpt-6.1-sol`, batches 4 to 8 on Qwen3.8-27B.

| batch | model | `left_alone` | `codex` | `pro` |
|---|---|---|---|---|
| 1 | Sol | 78.7% | 82.1% | 79.4% |
| 2 | Sol | 77.7% | 82.9% | 82.2% |
| 3 | Sol | 86.7% | 90.7% | 90.0% |
| 4 | Qwen | 69.1% | 66.4% | 66.9% |
| 5 | Qwen | 68.1% | 65.7% | 74.4% |
| 6 | Qwen | 78.3% | 81.4% | 86.2% |
| 7 | Qwen | 76.4% | 78.7% | 84.2% |
| 8 | Qwen | 67.9% | 66.7% | 77.4% |
| batches 1 to 3 | Sol | 81.3% | 85.6% | 84.2% |
| batches 4 to 8 | Qwen | 71.7% | 71.3% | 76.9% |
| all 800 (95% CI) | | 75.1% (71.8 to 78.3) | 75.7% (72.4 to 78.8) | 79.1% (75.9 to 82.3) |

Paired differences on the same appeals (bootstrap over appeals, 2,000 draws, 95% CI): over all 800, `pro` minus `codex` +3.3 points (+0.9 to +5.8), `pro` minus `left_alone` +4.0 (+1.1 to +6.9), `codex` minus `left_alone` +0.7 (-2.5 to +4.0). Over batches 4 to 8: +5.6 (+2.2 to +9.3), +5.2 (+0.9 to +9.7) and -0.4 (-5.0 to +4.3). These intervals cover which appeals were drawn, not how differently an improver might act in another run.

Over all 800 appeals, `left_alone` made 133 wrongful denials, 29 wrongful approvals and left 54 appeals undecided; `codex` 52, 70 and 29; `pro` 75, 56 and 15. Accuracy (not balanced) was 73.0%, 81.1% and 81.8%.

#### What each improver changed

Each cell gives the change and the approval result: mean balanced accuracy over 3 runs on every held-out appeal so far (20 per batch, never revealed), candidate against current version. Both improvers stayed within their rerun budget in every round, and no round's records carry an integrity flag.

| round | held out | `codex` | `pro` |
|---|---|---|---|
| 1 | 20 | sparse residential treatment summaries count as missing, not as evidence against; **shipped** (0.881 vs 0.798) | the same idea for ASAM level 3.1/3.5 residential appeals; **shipped** (0.833 vs 0.798; first trial lost to a harness bug, rerun) |
| 2 | 40 | do not infer necessity from a numeric score or an incidental finding alone; not shipped (0.917 vs 0.933) | the residential rule widened to all residential appeals; **shipped** (0.917 vs 0.906) |
| 3 | 60 | tested widening its residential rule to other treatments; no change | omissions count as unknown in every review type; not shipped (0.819 vs 0.893) |
| 4 | 80 | tested a counterevidence rule; no change | output limit 4,096 to 8,192 tokens and request limit 12 to 16; **shipped** (0.775 vs 0.726; undecided 0.0 vs 3.0) |
| 5 | 100 | tested two prompt clarifications; no change | request limit 16 to 20; **shipped** (0.756 vs 0.745) |
| 6 | 120 | at most three precedent searches per appeal; **shipped** (0.748 vs 0.726) | proton-beam rule; **shipped** (0.786 vs 0.781) |
| 7 | 140 | tested a rule on patient-specific criteria; no change | ABA dose and setting need patient-specific support; **shipped** (0.813 vs 0.788) |
| 8 | 160 | limit the missing-summary presumption to residential appeals; **shipped** (0.797 vs 0.765) | named organs at risk count as evidence for proton beam; not shipped (0.772 vs 0.822) |

Round 8's changes were never scored on a new batch. Codex's shipped round 8 version wrongly denied 20.0 held-out appeals on average against 6.7 for the version it replaced, and left 9.3 undecided against 2.7; it won on balanced accuracy because it wrongly approved 5.3 against 16.7. The improvers' own cost, by the frameworks' estimates: Codex $0.87 and the ZenML Pro agent $0.39 over all eight rounds.

#### What the run showed

- **The gap came from appeals left undecided.** After the switch to Qwen, appeals ended without a decision when the model used up its 4,096-token output limit or its 12 requests. The ZenML Pro agent counted every session's ending in round 4 (7 token-limit and 3 request-limit stops in batch 4), raised both limits, and raised the request limit again in round 5 when 3 batch 5 appeals hit the new one. From batch 6, `pro` left 2 of 300 appeals undecided, `codex` 15 and `left_alone` 38.
- **Codex looked for the cause in the prompt.** In rounds 3, 4, 5 and 7 it tested prompt changes, found them worse on its reruns, and made no change. In round 4 its notes mention token-limit failures in its own test runs; it did not change the limits in any round of this run (in the first run it raised the output limit in round 7). Its round 6 search cap was aimed at appeals that ran out of requests while searching.
- **Held-out approval turned down changes that each improver's own tests favored**: Codex's round 2 change, and the ZenML Pro agent's round 3 and round 8 changes. In round 3 the rejected candidate would have made 5.0 wrongful approvals on the held-out appeals against 2.3.
- **The same version varies by several points between lines.** On batch 1 all three lines ran the starting version, and scored 78.7%, 82.1% and 79.4%.
- **What is being compared.** Codex worked from the shared instructions alone, as it would for a team without Kitaru expertise. The ZenML Pro agent also had our prompting: its skills, and in this run a sentence in its task line asking it to count every session's ending, a rule its skill also states but that it skipped there in the mini rounds. The first run, without the task-line sentence, showed no difference between the lines. So the result reads as bare Codex against the ZenML Pro agent with expert prompting; it does not say how much of the gap Kitaru's records would give without that prompting.

### First run (2026-10-27 to 2026-10-28)

Approval on the revealed appeals, and the ZenML Pro agent's instruction line without the counting sentence. Rows and round records moved to `work/published-20261028/`.

#### Over time (batches 1 to 8, 100 appeals each)

Balanced accuracy of each line on each new batch, decided by the version that was current before the batch's outcomes were revealed. Batches 1 to 3 ran on `gpt-6.1-sol`, batches 4 to 8 on Qwen3.8-27B.

| batch | model | `left_alone` | `codex` | `pro` |
|---|---|---|---|---|
| 1 | Sol | 81.2% | 80.1% | 79.4% |
| 2 | Sol | 78.4% | 78.4% | 77.7% |
| 3 | Sol | 86.7% | 90.0% | 85.3% |
| 4 | Qwen | 65.4% | 64.5% | 64.8% |
| 5 | Qwen | 76.6% | 73.7% | 71.2% |
| 6 | Qwen | 78.3% | 85.2% | 80.2% |
| 7 | Qwen | 72.2% | 74.2% | 80.0% |
| 8 | Qwen | 66.9% | 75.0% | 74.8% |
| batches 1 to 3 | Sol | 82.4% | 83.1% | 81.1% |
| batches 4 to 8 | Qwen | 71.8% | 74.1% | 73.8% |
| all 800 (95% CI) | | 75.5% (72.2 to 78.6) | 76.8% (73.4 to 80.2) | 75.6% (72.2 to 78.9) |

Paired differences on the same appeals (bootstrap over appeals, 95% CI): over all 800, `codex` minus `left_alone` +1.3 points (-1.6 to +4.1), `pro` minus `left_alone` +0.2 (-3.0 to +3.3), `pro` minus `codex` -1.2 (-4.0 to +1.3). Over batches 4 to 8: +2.4 (-1.5 to +6.4), +2.1 (-2.5 to +6.6) and -0.3 (-4.1 to +3.5). Every interval includes zero.

Over all 800 appeals, `left_alone` made 141 wrongful denials, 27 wrongful approvals and left 46 appeals undecided; `codex` 82, 47 and 35; `pro` 88, 69 and 10. Accuracy (not balanced) was 73.2%, 79.5% and 79.1%.

#### What each improver changed

Each cell gives the change and the approval result: mean balanced accuracy over 3 runs on every revealed appeal so far, candidate against current version. All changes were to the prompt or to one setting; neither improver changed the agent's code or tools.

| round | revealed | `codex` | `pro` |
|---|---|---|---|
| 1 | 20 | ASAM level 3.1/3.5 residential rule; not shipped (0.802 vs 0.823) | tested separating missing documentation from negative evidence; shipped nothing |
| 2 | 40 | residential treatment center rule; **shipped** (0.862 vs 0.760) | tested fact-matched precedent comparison; shipped nothing (first trial cut by DNS, retried) |
| 3 | 60 | acute rehabilitation after stroke rule; **shipped** (0.895 vs 0.884) | RTC/ASAM precedent comparison rule; **shipped** (0.878 vs 0.795) |
| 4 | 80 | limit on precedent searches; not shipped (0.762 vs 0.768) | concise reasoning and exact-treatment search first; **shipped** (0.748 vs 0.735; first trial cut by DNS, retried, 1 rerun over budget) |
| 5 | 100 | considered a higher output limit; no change | output limit 4,096 to 8,192 tokens; **shipped** (0.776 vs 0.770; first trial cut by DNS, retried) |
| 6 | 120 | proton-beam rule; **shipped** (0.814 vs 0.798) | verify the exact drug and diagnosis; **shipped** (0.786 vs 0.783; first trial cut by DNS, retried) |
| 7 | 140 | output limit 4,096 to 8,192 tokens; **shipped** (0.829 vs 0.818) | tested an ABA hours rule, it broke another appeal; shipped nothing |
| 8 | 160 | match evidence to the exact service and setting; **shipped** (0.816 vs 0.807) | match precedents on service, diagnosis and indication; **shipped** (0.843 vs 0.811) |

Round 8's changes were never scored on a new batch. The improvers' own cost, by the frameworks' estimates: Codex $0.69 and the ZenML Pro agent $0.57 over all eight rounds, retries included.

#### What the run showed

- **The noise is as large as the improvements.** On batches 1 and 2 all three lines ran the same starting version: they differed by up to 1.8 points on 100 appeals. On 20 appeals one candidate scored 0.969 and 0.719 in two runs minutes apart (round 1). The three-run approval rule shipped changes that won by 0.3 to 10.2 points on the revealed appeals; the lines that carried them ended within 1.3 points of the line that never changed.
- **The improvers traded wrongful denials for wrongful approvals.** Both improved lines made about 40% fewer wrongful denials than `left_alone`, and more wrongful approvals: `codex` 1.7 times as many, `pro` 2.6 times. Balanced accuracy weighs both errors equally; an insurer or a patient would not.
- **The model switch cost every line 7 to 11 points.** Against `left_alone`, `codex` was 0.7 points ahead before the switch and 2.3 after it, `pro` 1.3 behind and 2.0 ahead; all within the noise.
- **Both improvers found the same settings fix.** On Qwen, the original 4,096-token output limit left appeals undecided when the model's reasoning used it up. The ZenML Pro agent raised it to 8,192 in round 5, Codex in round 7. From batch 6, `pro` left 1 of 300 appeals undecided, `left_alone` 33.
- **The ZenML Pro agent shipped nothing twice after its own test showed harm** (rounds 1 and 7). Codex shipped nothing once (round 5).
- **Four of the eight ZenML Pro trials were cut by DNS failures**, none of Codex's. The host's VPN resolver failed for short spells; the ZenML Pro agent's instructions stop it at its first workspace error, while Codex retried failed commands. Each cut trial was rerun, whatever its approval result, with the budget the earlier attempt left. After the VPN was turned off, during round 6, no failure recurred.
- **A restarted ZenML Pro trial picked up from the stored workspace.** In round 6 the retried trial found the first attempt's experiment in the Kitaru workspace, read its results and resubmitted the same change in 5 minutes without a new rerun. A restarted Codex trial starts from nothing, because its notes and reruns lived in the dead container.

### Calibration batch (batch 0, 100 appeals, one attempt each)

| who decides | accuracy | balanced accuracy (95% CI) | decided | wrongful denials | wrongful approvals |
|---|---|---|---|---|---|
| always overturn | 69% | 50% | 100 | 0 | 31 |
| HICRIC classifier (no agent) | 74% | 75% | 100 | | |
| claims agent, Qwen3.8-27B (original model and settings) | 73% | 70.7% (60.1 to 80.4) | 93 | 14 | 6 |
| claims agent, gpt-6-luna | 73% | 77.8% (69.8 to 84.9) | 100 | 24 | 3 |
| claims agent, gpt-6.1-sol | 84% | 88.4% (83.1 to 93.2) | 100 | 16 | 0 |

Balanced accuracy is the mean of accuracy on upheld and on overturned appeals; an undecided appeal counts as wrong. CI: bootstrap over appeals. A wrongful denial is an upheld denial that the reviewer overturned.

On Qwen, the port scores inside the original benchmark's published range (70 to 76% accuracy on its own 150 appeals), which is evidence the port behaves like the original. Seven Qwen appeals ended undecided, four of them because the model's reasoning used up the original 4,096-token output limit.

### Reference classifier

HICRIC's DistilBERT appeal-outcome model, trained with HICRIC's own code: 73.7% accuracy on HICRIC's published test split (the paper reports 73.3%), and 73.4% balanced accuracy on all 3,131 usable 2025-2026 appeals. Per batch it ranges from 64% to 78% balanced accuracy. Details: [`harness/hicric/README.md`](harness/hicric/README.md).

## Trust status

Checked:
- The precedent library is byte-identical to `decision-agents`' (same sha256 as its `data/SHA256SUMS`), built from the same CSV.
- The agent's tool definitions, system prompt and settings were compared request by request with the original and are identical; the remaining differences are listed in [`harness/claims_agent/README.md`](harness/claims_agent/README.md).
- Batch assignment is deterministic (two runs give identical files).
- Three mini rounds (10 appeals, 4 revealed) ran both improvers end to end. Inside each trial only the revealed appeals carried a ruling, and an attempt to score an unrevealed appeal in the Kitaru workspace was refused. In mini round 3 the ZenML Pro agent registered three versions and ran three Kitaru experiments on the revealed appeals, executed by the worker inside its own trial; no evaluation of an unrevealed appeal was stored.
- `round.py` survives a killed process, a cut network and a simulated freeze without losing rows or scoring an infrastructure failure as a wrong answer (section "Interruptions and resuming" in [`RERUN.md`](RERUN.md)).

Found while building it:
- In mini rounds 1 and 2 the ZenML Pro agent could rerun the agent either with the same plain `claims-rerun` tool Codex has or through Kitaru experiments. Both times it read the Kitaru workspace and then used only `claims-rerun`, although its own Kitaru skill says to verify a change with an experiment. The rounds use the setup a team would have: for the ZenML Pro arm, Kitaru experiments are the only rerun path.
- A Kitaru agent version registered with a working directory points at that directory, not a copy, so a version's code can change after it is registered. The improver edited and reverted one directory under three versions.
- A Kitaru replay that fails (here, the claims agent hitting its request limit) gets no evaluation, so an experiment's own scores leave that appeal out instead of counting it as wrong. The approval rule scores on the host and counts it as wrong.

Found while running the first run:
- The scan for agent runs outside an arm's counted rerun path matched commands that only name the episode module: `--help` calls, imports that call a read tool directly, and process listings that search for the module with `rg` or `sed`. Each false match was fixed in `round.py`, added to `scripts/test_outside_runs.py`, and every earlier decision recounted; a recounted decision keeps its old counts under `reruns.recounted`. One overrun is real: the round 4 retry of the ZenML Pro trial was told it had 3 reruns, used them, and the first attempt's 1 counts too. Since then a restarted trial is told the budget the earlier attempts left.
- The first approval on the open model (round 4) ran 8 appeals at a time and took 3 hours 11 minutes. From the round 4 retry on, `round.py` ran with `--concurrency 24`, and an approval of both arms took 15 to 101 minutes, growing with the number of revealed appeals.
- Codex's `claims-rerun` runs 6 appeals at a time and the ZenML Pro agent's Kitaru worker 4, so a ZenML Pro rerun of the same appeals takes longer within the same 45 minutes. This was set before the run and left unchanged.
- The audit after round 8 found 941 evaluations in the Kitaru workspace since the run started, all of revealed appeals, and no agent version registered by an improver run by a host worker.

Checked between the two runs, in mini rounds on 2026-10-28 (`--frontier-preset smoke-gpt-5-mini-tight`, an output limit of 1,200 tokens so that some appeals end undecided):
- Held-out approval ran on 4 appeals that no improver saw, none of them revealed. In one round the ZenML Pro agent's own test on the revealed appeals showed 0.58 against 0.25, and held-out approval rejected the candidate (0.583 against 0.667). In another, Codex raised the output limit after finding that 5 batch 1 appeals had hit it, and held-out approval shipped the change (0.833 against 0.417; undecided 0.0 against 1.7).
- With the Kitaru host made unreachable inside its trial for 90 seconds, the ZenML Pro agent retried the failed command after 10, 30 and 60 seconds, and the last retry succeeded. The agent's instructions now say to retry a network error up to three times before reporting it.
- The ZenML Pro agent's playbook now asks it to count how every session ended before studying the revealed ones. In the two rounds where some sessions ended undecided, it read that step, did not do it, and studied only the revealed appeals.
- The same rule then went into the ZenML Pro arm's instruction line (`arm_access` in `round.py`); the first run did not have it. In the next mini round the agent counted before choosing sessions, but it picked the 10 sessions by name, and the workspace still held the batch 1 sessions of an earlier mini run under the same names. It counted those (10 of 10 decided) instead of the round's own (6 of 10 decided). Codex, in the same round, found the 4 undecided appeals and raised the output limit, and held-out approval shipped it (0.750 against 0.417).
- The line now also names the agent version that recorded each batch, read from the batch's rows, and says that replays and earlier runs can carry the same session names. In the next mini round the ZenML Pro agent counted the round's own 10 sessions correctly (8 decided, 2 stopped at the output limit), raised the limit to 3,000 as its one change, tested it in one Kitaru experiment on 3 revealed appeals, and held-out approval shipped it (0.750 against 0.583; undecided 0.0 against 1.3). Codex made the same kind of change (4,096) and it shipped too (0.667 against 0.583).
- `--pro-gepa` gives the ZenML Pro arm GEPA 0.1.4 (in `/opt/gepa-venv` of its image) and a budget of appeal runs instead of experiment runs: each appeal in a Kitaru experiment run counts once, up to `--rerun-budget` times the revealed appeals so far, which is the number of appeal runs Codex's reruns allow. Its skill runs GEPA with each candidate registered as an agent version and scored by Kitaru experiments. In the one mini round with it, the agent read the GEPA instructions and did not run GEPA: they say it needs at least about ten scored sessions, and a mini round reveals 4. It raised the output limit by hand instead, used 9 of its 12 appeal runs, and held-out approval shipped it (0.833 against 0.500). GEPA has not yet run against a live workspace.

Found while running the second run:
- The ZenML Pro trial of round 1 finished with a candidate, and the harness failed it before approval. The harness fails a trial when a Kitaru command's output shows a login failure, so that a trial cannot quietly run without the workspace. It matched the error-kind list that `kitaru schema` prints, which includes the word for an authentication failure. The check now counts only a command result that reports `"ok": false` with an authentication error; on the 9 earlier ZenML Pro trials it finds nothing, and it still catches both of 2 constructed real failures. The round was stopped as round 2 began; Codex's round 1 trial and decision were kept, the ZenML Pro arm's round 1 records and batch 2 rows were set aside in `aside-pro-auth-scan-bug` folders (no Kitaru job of them was still pending), the attempt was marked `discarded` in `improve-attempts.json`, and the restarted trial got the full 3 reruns because nothing of the first attempt reached approval.
- The audit after round 8 found 104 evaluations in the Kitaru workspace since the run started, all of revealed appeals, and no agent version registered by an improver run by a host worker.
- No trial of either arm was cut by a network failure.

Checked by the run: the model switch end to end; the noise between unchanged runs of the same batch (batches 1 and 2, where all three lines ran the starting version).

## Harbor status

`native` for the improvement rounds: each improver runs as a Harbor trial built by `harbor/round_task/`. The `codex` arm runs from this repository. The `pro` arm needs the ZenML Pro agent bundle, which is not public: `round.py` runs it when `PRO_AGENT_DIR` points at the bundle, and without it runs the other two lines (setup in [`harbor/round_task/README.md`](harbor/round_task/README.md)).

## Limitations

- One state's medical-necessity and experimental-treatment reviews, written decisions, not insurers' claim files.
- Case files are written by a model from decision texts that include the reviewer's reasoning; a regex drops files with outcome wording, but the choice of facts can still hint at the outcome. The same files feed the agent and the classifier.
- 100 appeals per batch gives a 95% interval about 10 to 20 points wide (10 near 90%, 20 near 70%) on balanced accuracy for one batch; the cumulative numbers are tighter.
- Improver runs are one attempt per round and arm, unless a crash or network failure cuts one short; then the arm reruns, and the reruns it used before the crash still count against its budget. Each design ran once, and the two runs ranked the lines differently, so a third run could too.
- In the first run the ZenML Pro arm lost four trials to network failures and Codex none; the retries were given what was left of the budget, so those rounds gave the ZenML Pro agent fewer fresh reruns.
- In the second run the ZenML Pro arm's task line carried a hint from us (count every session's ending first, and which version recorded each batch) that a customer would not type, and it points at the failure the agent went on to fix. The product's skill states the same rule, but the agent followed it only from the task line. Moving the rule into the product's always-loaded prompt would make the comparison exactly bare Codex against the shipped product.

## Provenance

Built on [`decision-agents`](../decision-agents/) (claims harness at commit `2542d57`): the case-file prompt, the leak check, the agent's prompt, tools and settings, and the precedent library come from there. Built by Alex Strick van Linschoten (ZenML) with coding agents, 2026-10-27.
