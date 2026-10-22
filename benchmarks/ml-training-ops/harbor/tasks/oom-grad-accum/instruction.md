The training job in /app (`python /app/train.py`) is killed by the cluster for exceeding its
memory limit: jobs may use at most 1.2 GB of resident memory, and this one peaks far above that.
Make it fit under 1.2 GB without changing what it computes: the effective batch size per optimizer
step (32768 samples), the model, the optimizer, the learning rate, the number of optimizer steps
and the data must stay the same, and the final weights must match what the original job would
have produced (up to floating-point noise). The job must still save its weights to /app/model.pt.
