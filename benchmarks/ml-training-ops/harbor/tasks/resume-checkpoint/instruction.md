Our training job (/app/train.py) can be interrupted and resumed: `python /app/train.py --steps N
--ckpt PATH` trains up to step N and saves a checkpoint, and `--resume` continues from it. After a
resume, the loss jumps and the final model differs from an uninterrupted run. Fix checkpointing
and resuming so that training for 300 steps in one go and training 150 steps, then resuming to 300,
produce the same final weights (up to floating-point noise). Keep the model, optimizer (Adam),
learning-rate schedule and data order as they are.
