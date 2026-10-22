# Our preemptible training job keeps corrupting itself

`/app/train.py` runs on spot capacity. The scheduler preempts it at arbitrary moments with
`SIGKILL` (no warning, no grace period) and restarts the same command:

    python /app/train.py --ckpt-dir /app/ckpt --steps 200

The job resumes from the newest checkpoint in `--ckpt-dir`. Lately:

- after some preemptions, the job crash-loops on restart (see `/app/logs/restarts.log`),
- the evaluation service, which picks up the newest `ckpt-*.pt` from the same directory at any time,
  sometimes fails to load it,
- runs that were preempted end with different weights than runs that were not, even though the
  data and initialisation are deterministic.

Make checkpointing and resumption robust:

- At every moment, including while a checkpoint is being written and right after a `SIGKILL` at
  any instruction, every file matching `ckpt-*.pt` in the checkpoint directory must be a complete,
  loadable checkpoint. Other files (e.g. temporary files) may exist.
- A preemption must never destroy a checkpoint that was already complete unless a newer complete
  one exists.
- After any sequence of preemptions and restarts, the final weights (`<ckpt-dir>/final.pt`, a
  `state_dict`) must equal those of an uninterrupted run.

Keep the model, optimizer, data, number of steps, save interval and the command-line interface.
Checkpoints must stay `torch.save`d dicts with the keys `model`, `opt` and `step`, keep at most two
complete `ckpt-*.pt` files around, and use no more than one directory (the `--ckpt-dir`).
