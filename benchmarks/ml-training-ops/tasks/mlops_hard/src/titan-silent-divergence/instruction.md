# The 200M acceptance run no longer matches, and the loss looks too good

Our torchtitan fork lives in `/app/titan` (intentional changes listed in `/app/FORK_CHANGES.md`).
Every change to the training stack must pass the acceptance run: the internal 200M model, 1000 steps
on 2 GPUs, deterministic, launched by `/app/run_reference.sh` with the cluster defaults in
`/app/cluster_env.sh`. It takes about 6 minutes and writes its per-step losses to
`/app/reference_losses.json`. On a healthy setup it reproduces the platform team's golden curve
(`/app/golden_losses.json`) bit for bit.

It doesn't anymore. The final loss is now far below the golden curve, and some people want to
ship that as an improvement. Nobody has changed the training code since the golden curve was
recorded.

Find out why, and make the acceptance run reproduce the golden curve again: mean absolute loss
difference over steps 901-1000 below 0.002, and no step off by more than 0.01.

Rules:
- The training corpus in `/data/corpus` is shared and read-only. Don't modify, move or add files
  there. The fork can skip shards by name (`training.exclude_shards` in the run's config).
- Don't change the training code, the model, the optimizer or the other hyperparameters in
  `internal_200m.toml`. `exclude_shards` is the only setting there you may change.
- You may fix the job's environment (`/app/cluster_env.sh`) where it is wrong for this run.
- The grader runs its own copy of `run_reference.sh` against your `/app`.
