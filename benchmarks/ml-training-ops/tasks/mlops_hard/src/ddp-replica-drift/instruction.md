# Replicas drift apart after the GradSync migration

Our data-parallel training job lives in `/app`. It is launched with

    torchrun --standalone --nproc_per_node=4 /app/train.py --steps 300 --out /app/out

Two weeks ago we replaced `DistributedDataParallel` with our own gradient synchronisation
(`trainer/dist_utils.py`, "GradSync") because DDP's bucketing was slow for our small models.
Since then:

- the checkpoint saved by rank 0 evaluates worse than the training-time accuracy that some other
  ranks report,
- runs with 4 workers converge differently from runs with 2 workers on the same global batch,
- loss curves on rank 0 "look fine", so nobody noticed for a while.

See `/app/logs/` for the on-call notes and a recent training log.

Fix the training code so that data-parallel training is correct: every rank must hold identical
weights throughout, and the result must be the same (up to floating-point noise) as training the
same model on the full global batch in a single process, whatever the number of workers (for example 2, 3 or 4).

Constraints:
- Keep using GradSync (do not switch back to DDP), the gloo backend, the model, the optimizer and
  its hyperparameters, the global batch size and the data pipeline semantics (the global batch for
  each step and how it is split across ranks).
- Keep the command-line interface. At the end of training every rank must still write its final
  weights to `<out>/rank<r>.pt` (a `state_dict`), and rank 0 writes `<out>/model.pt`.
