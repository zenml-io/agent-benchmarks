# Resume a sharded-optimizer checkpoint on a different number of workers

Our training job (`/app/train.py`, optimizer in `/app/trainer/zero.py`) uses a ZeRO-1 style
sharded Adam: every rank keeps the Adam moments for one slice of the flattened parameters and
writes them to its own file at checkpoint time.

Last night's run used 4 workers and was preempted after saving `/app/ckpt/step-60`. Only 3 workers
are available now, and the resume fails (see `/app/logs/run-w4.log`):

    torchrun --standalone --nproc_per_node=3 /app/train.py --steps 100 --resume /app/ckpt/step-60 --save /app/ckpt/step-100

Make resuming work for any number of workers, from a checkpoint written with any number of
workers. Training must continue exactly as if the run had never been interrupted: after resuming,
the weights must match those of an uninterrupted run (up to floating-point noise), and checkpoints
written after the resume must resume correctly too, again with any number of workers.

Keep the model, the data, the loss, the optimizer's algorithm and hyperparameters, the
command-line interface and the checkpoint layout (`model.pt` plus one
`optim-rank<r>-of-<world>.pt` per rank). Do not rely on converting `/app/ckpt/step-60` in place:
we have many such checkpoints, and the job must be able to resume directly from the original files.
