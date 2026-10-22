# Elastic training that gives the same answer however the cluster behaves

`/app/train.py` is our data-parallel training job. On the spot cluster it is launched as

    torchrun --standalone --nproc_per_node=<W> train.py --ckpt-dir /app/ckpt

and every launch can be killed (`SIGKILL`, the whole process group, at any moment, including while
a checkpoint is being written). The scheduler then relaunches it with whatever number of workers is
available (W between 2 and 5, different each time). The job must resume from where it left off.
Rank 0 writes `<ckpt-dir>/final.pt` (the model `state_dict`) when training is done.

`/app/reference.py` is the specification: a single-process definition of exactly what training
computes (data per step, dropout masks, loss, optimizer, schedule). Our auditors require that the
final weights of the distributed job match `python reference.py` (to within 1e-4) for any number
of workers and any history of kills and relaunches. Today they don't, even without failures.

Fix `train.py`. Keep the command-line interface, the checkpoint directory layout (`ckpt-*.pt`
files plus `final.pt` in `--ckpt-dir`), gloo, and the specification itself: don't edit
`reference.py`, the grader uses its own copy. Importing from it is fine.
