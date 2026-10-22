# Nightly fine-tune gets OOMKilled

The nightly job (`/app/train.py`, 20k steps) runs in a pod with an 8 GiB memory limit and gets
OOMKilled after a few thousand steps. Its memory keeps growing for the whole run (see
`/app/logs/`); you can reproduce the growth locally with fewer steps, e.g.
`python /app/train.py --steps 1500 --out /tmp/out`.

Find and fix what makes memory grow with the number of steps, so that peak memory stays flat
however long the job runs.

The job must keep doing what it is documented to do: read the docstrings and comments in
`/app/trainer/`. The augmentation, the hard-example replay (with its documented capacity), the model,
optimizer, hyperparameters and data must keep their intended behaviour, and training results must
not change except where a bug made the code deviate from its documented behaviour. `metrics.json`
must keep `loss_history` and `grad_norm_history` with one number per step.
