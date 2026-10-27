# Claims over time: improving an appeals agent batch by batch

## Question

When a claims-review agent meets new cases in batches, with only a few outcomes coming back each time, how much does each round of improvement help, and does an improver that works through recorded traces and replays (the ZenML Pro agent with Kitaru) do better, or more cheaply, than a strong coding agent working from trace files (Codex)?

## Status

**In progress: the harness is built and checked; no improvement round has run.** Built and checked on 2026-10-27: the case stream, the agent port, the reference classifier, both improver arms in Harbor, and three mini rounds end to end. Spend so far: about $9 (case-file extraction $3.19 on Modal's bill; classifier training about $1.60 of GPU time; calibration runs about $2.50; smoke tests and mini rounds about $1.50; OpenAI costs are the frameworks' own estimates, not checked against the bill).

## Design

- **Cases.** California Independent Medical Review appeals from 2025 and 2026 ([CalHHS open data](https://data.chhs.ca.gov/dataset/independent-medical-review-imr-determinations-trend)): a health plan denied a treatment, the patient appealed, an independent reviewer upheld or overturned the denial. The agent reads a facts-only case file and a library of 19,374 earlier decisions (2016-2023), and decides. It is graded by exact match against the real ruling.
- **Stream.** 3,131 usable appeals in filing order, cut into 9 equal windows. One window gives the calibration batch (batch 0), the others give batches 1 to 8. Each batch is 100 appeals drawn at random from its window; 20 per batch are "revealed", meaning their ruling becomes available to the improvers after the batch is scored. `data/stream.jsonl` lists IDs, batches and revealed flags. Rulings stay out of the repository until the experiment ends.
- **Lines.** `left_alone` (the starting agent, never changed), `codex` and `pro` (each improved once per round). Each round: every line decides the new batch, the batch is scored, its outcomes are revealed, each improver proposes one change in a sealed Harbor trial, and a fixed rule ships the change only if its balanced accuracy on every revealed appeal so far is at least the current version's.
- **Model switch.** Rounds 1 to 3 run the claims agent on `gpt-6.1-sol`. Before batch 4, every line switches to Qwen3.8-27B served by vLLM, the cheaper open model the original agent ran on.
- **Fairness rules.** Both improvers run on `gpt-6-luna`, get the same instructions except one line (`harness/improver_instructions.md`), the same revealed rulings, the same budget (3 reruns on the revealed appeals, 45 minutes; Codex reruns with a `claims-rerun` tool, the ZenML Pro agent only through Kitaru experiments, and any other run of the agent found in an improver's command log counts as over budget) and the same network (the model API, and for `pro` the Kitaru workspace). An improver can never read the ruling of an unrevealed appeal, and no score of an unrevealed appeal is written anywhere an improver can read.

## Results

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

Found while building it:
- In mini rounds 1 and 2 the ZenML Pro agent could rerun the agent either with the same plain `claims-rerun` tool Codex has or through Kitaru experiments. Both times it read the Kitaru workspace and then used only `claims-rerun`, although its own Kitaru skill says to verify a change with an experiment. The rounds use the setup a team would have: for the ZenML Pro arm, Kitaru experiments are the only rerun path.
- A Kitaru agent version registered with a working directory points at that directory, not a copy, so a version's code can change after it is registered. The improver edited and reverted one directory under three versions.
- A Kitaru replay that fails (here, the claims agent hitting its request limit) gets no evaluation, so an experiment's own scores leave that appeal out instead of counting it as wrong. The approval rule scores on the host and counts it as wrong.

Not checked: any full round; the model switch end to end; the noise between two unchanged runs of the same batch (planned: round 1 runs the starting version three times, once per line).

## Harbor status

`native` for the improvement rounds: each improver runs as a Harbor trial built by `harbor/round_task/`. The `codex` arm runs from this repository. The `pro` arm needs the ZenML Pro agent bundle, which is not public: `round.py` runs it when `PRO_AGENT_DIR` points at the bundle, and without it runs the other two lines (setup in [`harbor/round_task/README.md`](harbor/round_task/README.md)).

## Limitations

- One state's medical-necessity and experimental-treatment reviews, written decisions, not insurers' claim files.
- Case files are written by a model from decision texts that include the reviewer's reasoning; a regex drops files with outcome wording, but the choice of facts can still hint at the outcome. The same files feed the agent and the classifier.
- 100 appeals per batch gives a 95% interval about 10 to 20 points wide (10 near 90%, 20 near 70%) on balanced accuracy for one batch; the cumulative numbers are tighter.
- Improver runs are one attempt per round and arm.

## Provenance

Built on [`decision-agents`](../decision-agents/) (claims harness at commit `2542d57`): the case-file prompt, the leak check, the agent's prompt, tools and settings, and the precedent library come from there. Built by Alex Strick van Linschoten (ZenML) with coding agents, 2026-10-27.
