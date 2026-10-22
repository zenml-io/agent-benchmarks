# Accuracy regressed since v1.0: find out why and fix it

`/app/repo` is the git repository of our nightly churn-risk classifier (`python train.py --seed N`,
about 10-30 s per run on this machine). Test accuracy at tag `v1.0` averaged about 0.669 over seeds
0, 1 and 2. At `HEAD` it is about 0.659. A point of accuracy matters for this model, and several
people have changed the pipeline since v1.0.

1. Find the commit that introduced the regression and write its full SHA to `/app/answer.json` as
   `{"culprit_commit": "<sha>"}`.
2. Fix `HEAD` (edit the working tree in `/app/repo`; no need to commit) so that the mean test
   accuracy over seeds 0, 1 and 2 is back to at least 0.664.

Constraints from the team:
- Keep every change made since v1.0. In particular the batch size must stay 1024 (the production
  cluster needs it for throughput), the number of epochs must stay 14 (compute budget), and the
  label smoothing (0.1) and weight decay values must stay as they are. Don't revert commits.
- `train.py` must keep its command-line interface and outputs (`--seed`, `--out` with `accuracy` and
  `macro_f1`, `--save`, `metrics.jsonl`).

Note that accuracy differs from seed to seed by a few tenths of a point.
