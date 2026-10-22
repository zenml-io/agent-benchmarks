# Gang scheduler

`controller.py` schedules distributed training jobs onto a GPU cluster. A job is a gang of pods:
it makes progress only while all its pods are bound to ready nodes.

Develop against the simulator in `kube/sim.py` (an API server + cluster model: optimistic
concurrency, watch expiry, rate-limited lists, transient errors, node failures, other tenants'
pods). `python run.py --seeds 1 2 3` runs your controller and checks the rules.

Rules (checked every tick):
1. **All or nothing.** No job may hold some but not all of its pods on nodes for more than 5
   consecutive ticks. This includes jobs that lose members when a node fails.
2. **No crashes.** `Controller.step()` must not raise, whatever the API does.
3. **Everything finishes.** Every feasible job (one that fits in the cluster) must finish by tick
   1000. Jobs that can never fit must not hold up the others, and no feasible job may starve.

The controller sees the cluster only through `Api` (see its docstring). It is constructed once with
`Controller(api)`, and `step()` is called once per tick.
