# Underwriting agent: cost of a correct decision

## Question

What does a correct decision cost when 12 models run the same insurance underwriting agent, and how much of the gap between models is the prompt?

## Status

Complete. Runs on 2026-10-21 (first prompt, tuning, effort, step-level screen, Kitaru full replay) and 2026-10-22 (shared prompt). Total spend $259.15 at list prices, every model call included (agent, simulated underwriter, judges, prompt optimizer, pilots, replays); the itemized log is in [RERUN.md](RERUN.md#7-full-rerun). Run by Hamza Tahir (ZenML) with Claude Code agents.

The setup: 252 commercial-insurance cases from Snorkel AI's public multi-turn underwriting datasets (Apache-2.0). The insurer's database, appetite guide and guidelines are not published, so they were rebuilt from the published traces (`env/`). An agent with six read-only tools over that database (`harness/run.py`) talks to a simulated underwriter (Claude Haiku 5.5) who holds the application, and ends the case with `FINAL ANSWER:`. Two LLM judges (GPT-6 Luna, Claude Haiku 5.5) compare the answer with Snorkel's reference, and GPT-6.1 Sol breaks ties. Open-weight models ran on one commercial inference provider, called `provider-a` here.

## Results

All numbers below are copied from [`results/underwriting.json`](results/underwriting.json), which `scripts/export.py` rebuilds from the committed per-case rows. Accuracy counts every scored case: step-limit, turn-limit, empty-reply and API-error cases count as wrong. Cost per correct decision is the agent's own model cost (not the simulator or the judges) divided by the number of correct cases. Intervals are paired bootstrap 95% intervals (4,000 resamples) against the stated reference.

### 1. One prompt for every model (first run, all 252 cases)

| Model | Correct | Accuracy | vs Opus 5.5, pts [95% CI] | Cost per correct decision | Model calls per case |
|---|---|---|---|---|---|
| DeepSeek V4 Pro (open) | 246/252 | 0.9762 | +0.4 [-2.0, +2.8] | 3.5541¢ | 9.12 |
| Claude Opus 5.5 | 245/252 | 0.9722 | reference | 5.2592¢ | 6.53 |
| GLM 5.3 (open) | 239/252 | 0.9484 | -2.4 [-5.6, +0.4] | 8.2513¢ | 10.67 |
| GLM 5.3 Flash (open) | 233/252 | 0.9246 | -4.8 [-9.1, -1.2] | 0.9750¢ | 10.98 |
| DeepSeek V4.1 Flash (open) | 230/252 | 0.9127 | -6.0 [-9.5, -2.4] | 2.1011¢ | 9.18 |
| Claude Sonnet 5.5 | 224/252 | 0.8889 | -8.3 [-12.7, -4.0] | 4.0590¢ | 8.34 |
| Claude Haiku 5.5 | 220/252 | 0.8730 | -9.9 [-14.3, -5.6] | 0.4997¢ | 8.85 |
| GPT-6 Luna | 219/252 | 0.8690 | see Trust status | 0.1903¢ | 7.87 |
| MiniMax-M3 (open) | 218/252 | 0.8651 | -10.7 [-15.5, -6.0] | 1.7512¢ | 9.95 |
| Qwen3.8 27B (open) | 212/252 | 0.8413 | -13.1 [-18.3, -8.3] | 3.7067¢ | 10.39 |
| GPT-6.1 Sol | 211/252 | 0.8373 | -13.5 [-18.7, -8.7] | 2.0123¢ | 7.09 |
| gpt-oss-120b (open) | 150/252 | 0.5952 | -37.7 [-44.0, -31.3] | 0.9900¢ | 8.56 |

GPT-6 Luna: the original write-up shows 218/252 and -10.7 [-15.1, -6.7]; the committed rows give 219/252 and -10.3 [-14.7, -6.3]. See Trust status.

Per question type (`per_type.first_prompt_all_cases` in the export): the weak spots were policy limits (17 cases; 0.5294 to 0.6471 for DeepSeek V4.1 Flash, GLM 5.3, GLM 5.3 Flash and MiniMax-M3) and product recommendations (72 cases; 0.6667 to 0.7778 for Qwen3.8 27B, MiniMax-M3 and Sonnet 5.5). Agent-loop failures: gpt-oss-120b sent unreadable tool calls in 28 cases, Qwen3.8 27B ran out of its 30 calls in 17, and GPT-6.1 Sol put `FINAL ANSWER:` on a question to the underwriter in 15 of its 41 wrong cases (text-pattern classification).

### 2. Held-out cases: first prompt, a shared rewritten prompt, and each model's own rewritten prompt

The 252 cases were split into 84 learning and 168 held-out cases (stratified by question type, `env/split.json`). Prompts were rewritten by Claude Opus 5.5 from failures on the learning cases only. The "shared" prompt is Sonnet 5.5's rewritten prompt (`results/tuned/prompts/sonnet-5.5/v1.txt`), used unchanged on every model. Deltas are against the same model's first-prompt run on the same held-out cases.

| Model | First prompt | Shared prompt | Δ pts [95% CI] | Own rewritten prompt | Δ pts [95% CI] | Cost per correct: first → shared |
|---|---|---|---|---|---|---|
| GLM 5.3 Flash | 154/168 (0.9167) | 167/168 (0.9940) | +7.7 [+3.6, +12.5] | 163/167 (0.9760) | +6.0 [+1.8, +10.8] | 0.9830¢ → 0.9185¢ |
| Claude Sonnet 5.5 | 150/168 (0.8929) | 167/168 (0.9940) | +10.1 [+5.4, +14.9] | (the shared prompt is its own) | | 4.1068¢ → 2.7274¢ |
| Claude Haiku 5.5 | 144/168 (0.8571) | 166/168 (0.9881) | +13.1 [+8.3, +18.5] | 163/167 (0.9760) | +12.0 [+6.6, +17.4] | 0.5208¢ → 0.3792¢ |
| DeepSeek V4 Pro | 163/168 (0.9702) | 166/168 (0.9881) | +1.8 [-0.6, +4.8] | 165/168 (0.9821) | +1.2 [-1.8, +4.2] | 3.5556¢ → 3.2660¢ |
| GPT-6.1 Sol | 138/168 (0.8214) | 165/168 (0.9821) | +16.1 [+10.1, +22.0] | 164/168 (0.9762) | +15.5 [+9.5, +21.4] | 2.0134¢ → 1.7822¢ |
| DeepSeek V4.1 Flash | 154/168 (0.9167) | 165/168 (0.9821) | +6.5 [+2.4, +11.3] | not tuned | | 2.0617¢ → 1.8088¢ |
| GLM 5.3 | 159/168 (0.9464) | 165/168 (0.9821) | +3.6 [+0.6, +6.5] | not tuned | | 8.0935¢ → 7.3684¢ |
| Claude Opus 5.5 | 163/168 (0.9702) | 164/168 (0.9762) | +0.6 [-3.0, +4.2] | 165/168 (0.9821) | +1.2 [-1.2, +3.6] | 5.2628¢ → 5.1198¢ |
| MiniMax-M3 | 142/168 (0.8452) | 162/168 (0.9643) | +11.9 [+6.5, +17.3] | not tuned | | 1.7681¢ → 1.8243¢ |
| GPT-6 Luna | 141/168 (0.8393) | 152/168 (0.9048) | +6.5 [+0.6, +12.5] | no rewrite improved its learning score | | 0.2011¢ → 0.1872¢ |
| gpt-oss-120b | 94/168 (0.5595) | 146/168 (0.8690) | +31.0 [+22.0, +39.9] | 128/168 (0.7619) | +20.2 [+10.7, +29.8] | 0.9823¢ → 1.1500¢ |
| Qwen3.8 27B | 140/168 (0.8333) | 139/168 (0.8274) | -0.6 [-7.7, +6.5] | not tuned | | 3.9380¢ → 5.3304¢ |

n = 167 where one case hit a harness (network) error and was dropped.

### 3. Noise floor and reasoning effort (held-out, 168 cases, vs the same model's first-prompt run)

| Condition | Model | Correct | Δ pts [95% CI] |
|---|---|---|---|
| Repeat, nothing changed (noise floor) | Claude Sonnet 5.5 | 154/168 | +2.4 [-3.6, +8.3] |
| Effort low | Claude Sonnet 5.5 | 122/168 | -16.7 [-24.4, -8.9] |
| Effort medium | Claude Sonnet 5.5 | 137/168 | -7.7 [-14.9, -0.6] |
| Effort low | Claude Opus 5.5 | 157/168 | -3.6 [-7.1, 0.0] |
| Effort high | Claude Opus 5.5 | 164/168 | +0.6 [-2.4, +3.6] |
| Effort high | Claude Haiku 5.5 | 142/168 | -1.2 [-8.3, +6.0] |
| Effort high | GPT-6.1 Sol | 154/168 | +9.5 [+4.2, +14.9] |
| Effort low | GPT-6.1 Sol | 142/167 | +3.0 [-3.0, +9.6] |
| Effort high | GPT-6 Luna | 141/166 | +1.2 [-5.4, +7.8] |

### 4. Grading checks

- Each judge alone against Snorkel's own correctness labels on its published traces: GPT-6.1 Sol 0.8750 (n=160, κ 0.75), Claude Haiku 5.5 0.9000 (n=150, κ 0.80), GPT-6 Luna 0.8917 (n=157, κ 0.78). The two-judge panel with tie-break was not validated as a unit.
- Judges grading themselves: re-grading the three judge-candidates' first-prompt answers with the other judges (Opus 5.5 breaking ties) moved GPT-6 Luna +1.6 pts (219 → 223 of 252), Haiku 5.5 -0.8 (220 → 218), GPT-6.1 Sol -0.8 (211 → 209).
- The two primary judges agreed on 1661 of 1738 first-prompt held-out answers (0.9557) and 1858 of 1898 shared-prompt answers (0.9789).
- Memorization probe (24 cases whose answers depend on the synthetic appetite table, asked with no tools or data): product recommendations 0 of 72 correct across models; appetite checks 41 of 216, explained by fire-risk reasoning on lodging and lessor businesses. No sign that models memorized Snorkel's answers.

### 5. Model-swap checks with Kitaru (Sonnet 5.5 as today's model, first prompt)

- **Step-level screen** (Kitaru model-swap analyzer, 250 recorded Sonnet calls replayed per candidate; `replay/comparison.json`, spend $15.85, rerun on an updated analyzer $15.62): same-tool agreement correlated with full-run accuracy (Spearman 0.73), its top 3 all held Sonnet's accuracy, but it ranked the cheapest model that holds (GPT-6 Luna) 11th of 12, and Sonnet matched its own recorded tool only 0.5833 of the time. A filter, not a picker.
- **Full replay in Kitaru** (48 cases recorded with Sonnet 5.5, then replayed end to end with a model override; `kitaru_replay/results.json`, spend $9.11): DeepSeek V4 Pro 47/48 vs Sonnet 43/48, +8.3 [+2.1, +16.7]; GLM 5.3 45/48, +4.2 [-6.2, +14.6]; GPT-6 Luna 41/48, -4.2 [-16.7, +8.3]; Haiku 5.5 39/47 vs 42/47, -6.4 [-19.1, +6.4].

## Trust status

**Reproduced on 2026-10-22 from public data and committed rows (no model calls):**
- Snorkel's three parquet files and the four Census files download byte-identical to the original run's copies; the environment rebuild (`scripts/fetch_data.sh`) produces a byte-identical `env/insurance.db`, `env/tasks.json`, `env/extracted.json` and `env/guidelines.txt`; the oracle keeps 252 of 380 cases.
- The learning / held-out split (84 / 168) is reproduced by `scripts/make_split.py` from its stated rule (the original committed only the file).
- `scripts/check_tables.py`: the held-out tables (`results/tuned/summary.json`) regenerate identically; the export regenerates identically; the first-run table regenerates identically except GPT-6 Luna (below); spend recorded in the rows matches the spend log for the first run ($79.49), tuning and effort ($85.63), shared prompt ($47.38), self-judge regrade ($2.01) and memorization probe ($1.43).
- The step-level screen's summary (`replay/comparison.json`) regenerates exactly from the analyzer's raw outputs and the cached grades (rows, correlations, finalists), with no new grading calls. The raw outputs are not in this repo (see below), so this check can only be repeated from the private archive.
- The benchmark-side columns of the Kitaru full replay (each model's own run on the same 48 cases) match the rows.

**Not reproduced:** none of the model runs, judge verdicts, prompt rewrites, step-level replays or Kitaru replays were re-run (they cost money). The judges' verdicts are taken as recorded. The Kitaru experiment numbers (baseline and replay evaluations) need the Kitaru server they were stored in, which was not kept.

**Known inconsistencies** (also in `results/underwriting.json` → `inconsistencies`):
1. GPT-6 Luna's first-run count: the original write-up and `results/tables.md` / `results/summary.json` / `results/report.html` show 218/252 with one API error; the committed rows give 219/252. Two API-error cases were re-run, and the summary was written after one re-run had finished and before the other. The export's accuracy uses the rows (219) but its paired interval (-10.7 [-15.1, -6.7]) comes from the stale summary; from the rows it is -10.3 [-14.7, -6.3].
2. `harness/report.py` draws all bootstrap intervals from one random stream in the order the filesystem lists `results/runs/`, so intervals can shift by up to 0.4 pts on another machine. `scripts/check_tables.py` replays the original order.
3. The original write-up's tuned-prompt section has slightly different intervals for five arms (for example Sonnet 5.5 tuned +10.1 [+5.4, +15.5] vs [+5.4, +14.9] here) because the shared-prompt arms, added a day later, shifted `tuned_report.py`'s random stream. Point estimates are the same.
4. The export's first `dataset.dropped_reason` said the 128 dropped cases are ones where the oracle disagrees with the reference. The oracle's own report says: 53 the rebuilt environment cannot resolve, 44 with no recoverable NAICS code, 25 whose reference uses a later environment version, and 6 where the oracle disagrees.
5. The analyzer's "Best for" picks in `replay/comparison.json` come from the Kitaru version used on 2026-10-21; Kitaru commit `0217140` produces different picks (its report logic changed). Everything else in that file reproduces.

Also worth knowing: in the Kitaru full replay, Sonnet's Kitaru-recorded baseline scored 43/48 while its own benchmark run scored 40/48 on the same cases. That is the same model run twice, and it shows how wide the noise is at n=48.

**Steps that would vet the results further:**
1. Smoke-rerun 20 held-out cases on two models (Claude Haiku 5.5 and GLM 5.3 Flash) with the shared prompt and compare with their committed rows. This costs about $0.30.
2. Hand-check 40 judge verdicts against the reference: 20 where the two judges disagreed and the tie-break decided, and 20 random passes, weighted to product recommendations, where the "exactly these lines" rule is strict.
3. Repeat the shared-prompt arm for Haiku 5.5, GLM 5.3 Flash and Opus 5.5 (3 runs each, about $40) to see whether the "near tie at 97.6-99.4%" holds beyond the 2.4-point single-repeat noise floor.
4. Tune a prompt on a non-Claude model's learning failures (for example GLM 5.3 Flash) and share it, to test whether the shared prompt favors Claude models.
5. Re-check the open-weight list prices (unverified at the time) and recompute cost per correct decision.
6. Read 20 of the 128 dropped cases to confirm that the environment rebuild, not the agent setup, is why they are unanswerable.

## Harbor status

`native` for the benchmark's own agent loop and for MCP-capable harnesses; checked on a 12-case sample, not yet run with a model. Everything is in [harbor/](harbor/README.md):

- **Tasks.** `harbor/generate_tasks.py` builds one task per case (all 252, one split, or a sample) from the rebuilt environment; the learning / held-out split is in each task's metadata, and `--split held` builds the held-out set alone. A 12-case sample (2 per question type) is committed in `harbor/tasks/`, listed in `harbor/dataset.toml` and the repo-root `registry.json` (`underwriting-sample`).
- **Tools and simulated user as an MCP server.** A sidecar next to the agent's (empty) container serves the six database and guideline tools, `ask_underwriter` (the original simulator, Claude Haiku 5.5, holding the application but not the answer; 12 replies at most) and `submit_final_answer` (first submission only), running the benchmark's own `harness/` code. The simulator's cost is recorded apart from the agent's.
- **Grading.** The original panel, not a structured-answer grader: the hidden test reads the submitted answer from the sidecar and runs `harness/judge.py` with GPT-6 Luna and Claude Haiku 5.5, GPT-6.1 Sol breaking ties, with `run_task`'s pass rule. No answer scores 0 without a judge call; API failures are counted as infrastructure errors.
- **Setups as config.** The benchmark's loop is the Harbor agent `underwriting_agent.agent:UnderwritingCopilot` (options `prompt_file`, `effort`; model keys from `src/models_client/models.py`); `harbor/setups/` has the first prompt, the shared rewritten prompt, three effort levels, and Claude Code and Codex as off-the-shelf setups.
- **Checked (2026-10-22, Modal):** oracle 60/60 (12 cases × 5), nop 0/12, three shortcuts (hedged answer listing every option, a final answer that asks a question, forged reward and answer files) 0/36, a reworded correct answer 12/12; 45 offline tests (judges, simulator and models mocked); the custom agent up to its first model call.
- **Left:** a paid pilot of the benchmark's loop against its committed rows (to confirm the port reproduces the original's accuracy within noise), 5-attempt runs, the four checks on the other 240 cases (oracle and nop cost little: about $0.0002 of judges per oracle answer), and a network block against looking answers up in Snorkel's public dataset (not enforced for compose tasks on Modal).

## Limitations

- One run per case per model and condition; differences under about 3 points are within run-to-run noise.
- The insurer's environment is reconstructed from published traces; 128 of 380 cases were dropped because the rebuild could not reproduce their reference answer.
- The underwriter is simulated (Claude Haiku 5.5), not a person.
- LLM judges agree with Snorkel's labels 87.5-90.0% of the time per judge (n=150-160); the panel was not validated as a unit. Three judges are also candidates; re-grading moved them by -0.8 to +1.6 pts.
- The first-run prompt was written once and never tuned; first-run rankings largely reflect how well each model copes with it.
- Prompt tuning: one optimizer (Opus 5.5), at most 2 rounds, 84 learning cases, one held-out run per prompt. The shared prompt was tuned on a Claude model and may favor Claude models.
- Effort settings were tested only on the five closed models.
- List prices on 2026-10-19; open-weight prices are from an unverified table, and all open-weight models ran on one provider (prices and behavior vary by provider).
- The failure categories in `results/underwriting.json` → `failures` (other than harness statuses) are a text-pattern classification, not judged labels.
- The Kitaru full replay covers 48 cases, and most of its intervals are wide. The step-level screen and the full replay used the first prompt only.

**Left out of this repo:** full transcripts (`results/transcripts/`, `results/tuned/transcripts/`, about 310 MB), run logs, the step-level analyzer's raw outputs (`replay/out/`, per-call candidate replies and endpoint metadata), `replay/jev_sound.json` (per-call judge probabilities), superseded pilot, smoke and first-pass rows, and the Kitaru server database. They stay in the private archive. A rerun of the first-prompt runs regenerates the transcripts, which prompt tuning and the step-level screen need. The rebuilt environment and Snorkel's data are fetched, not vendored.

## Provenance

Ported on 2026-10-22 from a private research repository (`benchmarks/underwriting`, last commit `84411cff33aa4085450ffcf28c2276f3f34efc84`). The agent client and price table are vendored from that repository's Haiku Tax benchmark into `src/models_client/`. The original run was by Hamza Tahir (ZenML) with Claude Code agents. Data: [Snorkel AI Multi-Turn Insurance Underwriting](https://huggingface.co/datasets/snorkelai/Multi-Turn-Insurance-Underwriting) and [its Code-Gen variant](https://huggingface.co/datasets/snorkelai/Multi-Turn-Insurance-Underwriting-Code-Gen) (Apache-2.0), plus US Census Bureau NAICS 2022 files and concordances (public domain). The Kitaru parts used [zenml-io/kitaru](https://github.com/zenml-io/kitaru) branch `feature/model-swap-analyzer` (kitaru 0.27.2+dev, plugin `plugins/packages/model-swap` 0.1.0); commit `0217140` is the reference commit for a rerun.
