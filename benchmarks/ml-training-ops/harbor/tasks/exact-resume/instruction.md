# Preempted runs don't reproduce

`/app/train.py` trains on spot capacity. The scheduler kills it with `SIGKILL` at arbitrary moments
and restarts the same command:

    python /app/train.py --ckpt-dir /app/ckpt

It resumes from the newest checkpoint. Checkpoint writes are already atomic and resuming no longer
crashes. But a run that was preempted ends with different weights than one that wasn't, even though
the data, initialisation and every random seed are fixed. Our reproducibility audit requires a
preempted run to end with exactly the same weights as an uninterrupted one (up to floating-point
noise below 1e-6), however many times and wherever it was preempted.

Fix it. Keep the model, data, optimizer, learning-rate schedule, dropout, batch size, number of
epochs, checkpoint interval and command-line interface. An uninterrupted run must produce the same
weights as it does today, and checkpoints keep their names (`<ckpt-dir>/ckpt-<step>.pt`). The final weights are saved to `<ckpt-dir>/final.pt` (a `state_dict`).
