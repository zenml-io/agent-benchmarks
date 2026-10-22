# The nightly training job blows its time slot

`/app/train.py` (code in `/app/trainer/`) trains our event scorer. In production it runs
`python train.py --steps 400` and more steps on larger nights, and it no longer fits in its slot.
Make the job much faster: we need the whole 400-step job to run at least 10x faster than it does now
on the same machine, and each training step at least 3x faster, so longer runs scale too.

What must not change:
- The data: `trainer.data.Events(n, seed)` must still produce the same features and labels for every
  row (`Events(n, seed)[i]` returns `(features, label)`). The feature transform is part of the
  model's contract.
- The model architecture (`trainer.model.Scorer`), the optimizer (AdamW, lr=1e-3), the batch size
  (256) and the number of steps.
- The outputs: `--out` metrics JSON with `accuracy`, and `train_log.jsonl` with one line per step.
  Test accuracy must stay at least 0.94.

You may change everything else, including numeric precision, how batches are produced and logging.
