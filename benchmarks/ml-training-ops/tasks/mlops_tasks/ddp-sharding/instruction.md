/app/train_ddp.py trains with torch.distributed (2 processes on CPU, gloo backend):
`torchrun --nproc_per_node 2 /app/train_ddp.py`. Each rank writes the sample indices it trained on
to /app/seen_rank{R}.json (one list per epoch). Training is slower than expected and the loss
curve looks like the job only sees half the data. Fix the data sharding so that in every epoch
each training sample is processed by exactly one rank, the two ranks together cover the whole
training set, and the order changes from epoch to epoch. Keep the model, optimizer, number of
epochs and per-rank batch size as they are.
