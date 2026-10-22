# Our torchtitan fork no longer reproduces its own training run

`/app/titan` is our internal fork of torchtitan (based on upstream v0.2.2, history squashed). Its
intentional changes are listed in `/app/titan/../FORK_CHANGES.md` (`/app/FORK_CHANGES.md`).

Before the last refactor sprint, we recorded the loss curve of a fixed reference run: the Llama-3
debug model, 200 steps on 2 GPUs, seed 42, deterministic mode. The curve is in
`/app/golden_losses.json`. `/app/run_debug.sh` runs that exact configuration (about a minute) and
writes the per-step losses to `/app/debug_losses.json`. On a correct fork this run is bit-for-bit
reproducible. Today the curve no longer matches, and nobody knows which change broke it. Some
people even like the new curve better.

Make the fork reproduce the golden curve again: the mean absolute loss difference over steps
151-200 must be below 0.001, and no step may differ by more than 0.005. Keep every intentional
change in `FORK_CHANGES.md`. Don't make them go away, and don't change the reference configuration
or `run_debug.sh`. The grader runs its own copy of the reference run against your `/app/titan`.
