# Multi-worker job dies at the end of the first epoch

The training job in `/app` runs fine on 2 workers, but on 3 workers it dies at the end of the
first epoch with a gloo error (on other days it has hung until the timeout). It's launched like this:

    torchrun --standalone --nproc_per_node=3 /app/train.py --n-train 19970 --epochs 3 --out /app/out

The failing run's logs are in `/app/logs/`. The person who launched it suspected the network and
already tried changing gloo environment variables and timeouts (see `/app/launch.sh`); that
didn't help.

Make the job finish reliably for any number of workers (2-8) and any training-set size (the
`--n-train` value in production changes every day as new data arrives). The trained model must
still be good. Every rank must end with identical weights.

Constraints:
- Keep the gloo backend, the model, the optimizer and hyperparameters, the per-rank batch size and
  the number of epochs. Keep every training example in use: no example may be skipped for a
  whole epoch.
- Keep the command-line interface. Every rank must write its final weights to `<out>/rank<r>.pt`;
  rank 0 also writes `<out>/model.pt` and `<out>/metrics.json` with the key `val_accuracy`.
