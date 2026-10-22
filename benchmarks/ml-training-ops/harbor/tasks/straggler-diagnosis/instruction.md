# Training throughput dropped by a quarter mid-run

Our 64-GPU pre-training run (8 hosts x 8 GPUs, synchronous data parallel, one rank per GPU) lost
about a quarter of its throughput partway through yesterday's run, and it never came back. The
on-call engineer saved everything we have under `/app/telemetry/`:

- `hostfile.txt`: the hosts in launch order (node_rank = line order). Each host runs local ranks
  0-7; global rank = node_rank * 8 + local_rank.
- `env/<host>.env`: the environment each host's workers were launched with.
- `step_times.csv`: per-step, per-rank timings (data loading, forward, backward, all-reduce wait,
  total).
- `gpu/<host>.csv`: GPU telemetry sampled every 10 s, indexed by the physical GPU index as
  `nvidia-smi` reports it.
- `rank0.log`: the training log of rank 0.
- `dmesg/<host>.log`: kernel logs.

Several things went wrong on the cluster that day, but only one of them explains the lasting
slowdown. We need to take the bad hardware out of the pool without draining healthy machines.

Write `/app/answer.json` with exactly these keys:

```json
{
  "host": "<hostname>",
  "physical_gpu": <int, the nvidia-smi GPU index on that host>,
  "global_rank": <int>,
  "start_step": <int, first training step at which the lasting slowdown is visible>,
  "cause": "<one of: network, data_loading, thermal, ecc_memory, clock_or_power_throttling, software>",
  "cordon": ["<every host that should be removed from the pool, and only those>"]
}
```
