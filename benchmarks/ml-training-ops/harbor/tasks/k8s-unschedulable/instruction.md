# The 32-GPU training job has been Pending for three hours

`/app/job/pytorchjob.yaml` is a Kubeflow `PyTorchJob` (1 master + 3 workers, 8 H100s each) that has
been stuck in `Pending` since it was submitted. There is no cluster access from this machine, but
the on-call engineer saved a snapshot of the cluster state and the scheduler's events in
`/app/cluster/` (read `README.md` there first, it has the platform team's policies).

Fix `/app/job/pytorchjob.yaml` so that the scheduler can place all four pods right now, given the
nodes and the pods already running in the snapshot, without breaking cluster policy.

Constraints:
- Keep the job's name, namespace, replica counts, image, command, `nprocPerNode`, volumes, and 8 GPUs
  and 32 EFA devices per pod.
- Each pod needs at least 1600Gi of memory and at least 160 CPUs (requests).
- All four pods must run in the same availability zone, and the spec must guarantee it.
- Edit only the job file; the snapshot describes the cluster as it is and changing it changes nothing.
