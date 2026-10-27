# HICRIC reference classifier

An outside yardstick for the claims agent: a small text classifier trained by someone else, on someone else's data, that predicts whether an IMR appeal will be upheld or overturned. If the agent cannot beat it on the same cases, the agent is not "pretty good" yet.

The classifier is the DistilBERT appeal-outcome model from HICRIC ([code](https://github.com/TPAFS/hicric), Apache-2.0; [paper](https://arxiv.org/abs/2508.03718); [data](https://huggingface.co/datasets/Persius/imr-appeals), CC BY-SA 4.0). HICRIC trained it on about 74,000 past external-appeal decisions from New York and California. The newest rows we could date (by matching them to the IMR CSV) are from 2023, and the dataset was last updated in December 2024. Every claims-over-time case is from 2025 or 2026, so for this classifier they are all out-of-time cases.

## What we did

1. **Weights: trained, not reused.** HICRIC has not published trained weights. The paper's abstract says models were released, but on 2026-10-27 Hugging Face listed no models under `Persius` or `TPAFS` (only the `hicric` and `imr-appeals` datasets), and the GitHub repo has no releases. So we trained it again with HICRIC's own code.
2. **Training.** `hicric_modal.py` clones HICRIC at commit `37d88ab` and calls its own functions (`load_and_split`, `create_metadata_model`, `CPUEvalTrainer`, `compute_metrics2`) with its `distilbert.yaml` settings: DistilBERT with HICRIC's metadata head, learning rate 8e-7, 20 epochs, batch 48, fp16, best epoch chosen by loss on a 20% slice of the train split. The data is the published `imr-appeals` train split at revision `c68b70e`. One H100, one run, one seed.
3. **Three deliberate differences from HICRIC's run.** (a) HICRIC's config points at an LLM-augmented train file that was never published, so we train on the published, non-augmented split, as HICRIC's own "hicric_pretrained" configs do. (b) We pad each training batch to its longest row instead of padding every 1,000 rows to the longest; attention masks hide padding, so the model sees the same thing, and training is about 3 times faster. (c) `torch.compile` is off, which changes speed, not results.
4. **Reproduction.** We scored the trained model on HICRIC's published test split (table below).
5. **Our cases.** We fed each 2025-2026 eligible case to the model and wrote `work/hicric/predictions.jsonl`.

## Reproduction on HICRIC's own test split

| | Accuracy | Macro F1 | ROC AUC (one-vs-rest) | n |
| --- | --- | --- | --- | --- |
| Paper, Table 2, DistilBERT | 0.733 | 0.727 | 0.878 | 9,745 |
| Paper, Table 2, ClinicalBERT | 0.740 | 0.717 | 0.889 | 9,745 |
| Our run, three classes, plain argmax | 0.737 | 0.770 | 0.881 | 9,920 |
| Our run, three classes, "Insufficient" only above 0.7 (HICRIC's eval threshold for DistilBERT) | 0.737 | 0.765 | 0.881 | 9,920 |
| Our run, forced uphold or overturn (how we use it) | 0.735 | 0.731 | | 9,920 |

Accuracy and ROC AUC match the paper within half a point. Our macro F1 is higher than the paper's. The likely reason: the published test split is not the paper's test split. The paper describes 9,745 rows with 175 "Insufficient"; the published split has 9,920 rows with 113 "Insufficient". The "Insufficient" class is easy for the model here (F1 0.85) and counts for a third of macro F1, so a different "Insufficient" set moves macro F1 much more than accuracy. We did not try to recover the paper's exact split.

## The input we give it for our cases

The classifier must never see the reviewer's conclusion. Three inputs were possible.

- **Option A: HICRIC's "background" cut of the IMR Findings text.** HICRIC trained a second model to cut the "facts" part out of each decision text, and the classifier was trained on those cuts. We rejected this for two reasons. First, HICRIC's cuts are not leak-free: in the 33,928 HICRIC rows whose full text has a clear point where the reviewer starts speaking ("The physician reviewer found...", "Findings:", "Final Result"), 35.8% of the cuts (40.9% in the test split) include a span that comes after that point, such as "The records provided for review indicate that this patient has not had a thorough evaluation...". So part of the paper's 73% likely comes from reading the reviewer's reasoning. Second, the IMR text format changed. The share of Findings texts that start with a case summary before the reviewer's own words fell from 98% in 2016 to 34% in 2024, 28.5% in 2025 and 0% in 2026. In the new format the whole text is the reviewer's narrative, with facts and reasoning mixed sentence by sentence, so there is no clean "facts" part left to cut.
- **Option B: only the first sentence of the Findings text** ("A patient has requested authorization and coverage for Taltz."). Leak-free and in the same words HICRIC's inputs open with, but it throws away all the clinical facts.
- **Option C (chosen): the facts-only case file the agent reads, flattened to prose.** `hicric_ref.py inputs` joins the case file's `request`, `condition`, `history` and `prior_treatments` into sentences in that order, which is the order HICRIC's background texts use ("A 64-year-old enrollee has requested X... This patient has a history of..."). This is the closest thing to HICRIC's training input that is leak-free, and it gives the classifier exactly the facts the agent gets, so the two are compared on equal information.

Cases without a usable case file (extraction failed, or the case file matched the leak check) fall back to option B, and every prediction records which input it used. The batches in `data/stream.jsonl` only contain cases with a usable case file, so the fallback only affects the "all eligible" row below.

**Leak check.** The same `LEAK` regex as `benchmarks/decision-agents/harness/claims_bench.py` runs on every flattened input. Case files that matched it were already dropped by the extraction step; on the inputs we built, it matched none (`inputs` prints the count). The regex is a word list, so it misses reasoning phrased in other words; on HICRIC's own inputs it matched 9.9% of rows, while the position check above found 35.8%.

**Overlap check.** No 2025-2026 case is a copy of a HICRIC row. `hicric_ref.py checks` compares word 8-grams of each case's Findings text (before "Final Result") with every HICRIC full text, ignoring 8-grams that appear in 5 or more HICRIC texts. Eight cases share more than half of their remaining 8-grams with one HICRIC text; all eight are residential mental-health cases written from the same reviewer template (the LOCUS level-of-care paragraph) about a different patient. The classifier never sees this text, since it reads the case file instead.

## Mapping HICRIC's labels to ours

HICRIC predicts three classes: Upheld, Overturned and Insufficient ("this description is too thin to call"). Our task always needs uphold or overturn, so we drop Insufficient and compare the other two: `p_overturn = P(Overturned) / (P(Overturned) + P(Upheld))`, and the prediction is overturn when `p_overturn >= 0.5`. This is what HICRIC's own threshold rule does whenever Insufficient is below its threshold. The raw three-class probabilities stay in `predictions.jsonl`, and `scores.json` counts how often Insufficient was the top class.

## Results on the 2025-2026 eligible cases

Truth is the real IMR determination from the CSV. Balanced accuracy is the mean of the recall on upheld cases and the recall on overturned cases, so a model that always says "overturn" scores 0.5 on it.

| Cases | n | Accuracy | Balanced accuracy | Recall, uphold | Recall, overturn | "Always overturn" accuracy |
| --- | --- | --- | --- | --- | --- | --- |
| All 2025-2026 eligible cases | 3,155 | 0.737 | 0.733 | 0.725 | 0.741 | 0.723 |
| With a usable case file (the input we chose) | 3,131 | 0.738 | 0.734 | 0.724 | 0.744 | 0.723 |
| 2025 only, usable case file | 2,614 | 0.741 | 0.738 | 0.732 | 0.744 | 0.727 |
| 2026 only, usable case file | 517 | 0.725 | 0.714 | 0.684 | 0.743 | 0.700 |
| Fallback to the request sentence (no usable case file) | 24 | 0.583 | 0.722 | 1.000 | 0.444 | 0.750 |
| Control: HICRIC's own test split, first background span only | 9,920 | 0.586 | 0.588 | 0.557 | 0.620 | |

How to read this:

- On 2025-2026 cases the classifier is about as accurate as on its own test split (0.738 against 0.735), even though these cases are two to three years newer than its training data. But plain accuracy barely beats always guessing "overturn" (0.723), because 72% of these cases were overturned. The number that shows real skill is balanced accuracy, 0.734: it catches 72% of upheld denials and 74% of overturned ones.
- The case files carry a lot of signal. The control row shows that the same model, given only the short opening span of each HICRIC test case (roughly what option B gives it), drops to 0.59. That fits the limitation below: the facts in a case file were picked by the reviewer, and they lean toward the outcome.
- "Insufficient" was the top class for 26 of 3,155 cases; each still gets uphold or overturn by the rule above.
- `scores.json` also has the numbers per batch of `data/stream.jsonl`. When we scored, that file dated from before extraction finished (6 of its 900 cases now lack a usable case file), so rerun `hicric_ref.py score` after the final stream is built. With that early stream, batch accuracy ranged from 0.70 to 0.82 (n = 100 each), which is about the spread you expect from 100 cases (a 95% interval is roughly plus or minus 0.09).

## Rerun

From `benchmarks/claims-over-time`, after the shared data build has written `work/candidates.jsonl`, `work/imr.csv` and (for option C) `work/case_files.jsonl`:

```bash
export MODAL_ENVIRONMENT=<your Modal environment>
uv run --with pyarrow python harness/hicric/hicric_ref.py fetch      # free
uv run --with pyarrow python harness/hicric/hicric_ref.py checks     # free, about 2 minutes
uv run --extra modal modal run harness/hicric/hicric_modal.py::train --limit 3000 --epochs 1   # smoke test, about $0.05
uv run --extra modal modal run harness/hicric/hicric_modal.py::train                           # about 16 minutes, about $1.05
uv run python harness/hicric/hicric_ref.py inputs                    # free
uv run --extra modal modal run harness/hicric/hicric_modal.py::predict                         # about $0.02
uv run --with pyarrow python harness/hicric/hicric_ref.py control
uv run --extra modal modal run harness/hicric/hicric_modal.py::predict --control               # about $0.04
uv run --with pyarrow python harness/hicric/hicric_ref.py score      # free; writes predictions.jsonl and scores.json
```

`train` and `predict` run as ephemeral Modal apps, which stop when the call returns. The trained model stays in a Modal Volume (`MODAL_HICRIC_VOLUME`, default `hicric-model`) so `predict` can run again without retraining; delete the volume to stop paying for its storage. `pyarrow` is only needed to read HICRIC's parquet files and is not in `pyproject.toml`.

## Cost

GPU cost is the local wall-clock time of each Modal call times the H100 list price ($3.95 per hour). That slightly overstates GPU time (it includes container start) and leaves out Modal's small CPU and memory charges. The training call took 955 s ($1.05), of which 896 s was the training loop itself. Prediction calls took 17 to 33 s ($0.02 to $0.04 each). As an upper bound, the eight Modal app runs for this piece (two smoke runs that failed on package versions, one smoke run that worked, the training run, and four prediction runs) were alive for about 1,455 s in total, which is $1.60 at the H100 price even though part of that was image building with no GPU attached. Total spent on this piece: between $1.20 and $1.60. Repeating the prediction call gave identical probabilities (largest difference 0.0).

## Limitations

- One training run with one seed. We did not measure run-to-run spread, so differences of a point or two between this classifier and anything else are within noise we have not measured.
- The input for our cases (a flattened LLM-written case file) is not the kind of text HICRIC trained on. It is closer than any leak-free alternative, but the classifier is still reading a slightly different style of text.
- The case files are written by an LLM from the reviewer's text. The extraction prompt tells it to keep only facts, but the facts it keeps were chosen by the reviewer ("the records document meaningful improvement on Taltz"). That colors the agent's input in the same way, so the comparison stays fair, but the classifier's score on our cases is not a pure "before the appeal" forecast.
- 2025-2026 cases are 72% overturned, against 47% in HICRIC's data, and the model was not recalibrated for that. Balanced accuracy is the fairer number; plain accuracy should be read next to the "always overturn" baseline.
