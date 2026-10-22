# Throughput dropped twice: find all the bad hardware

Our 64-GPU pre-training run (8 hosts x 8 GPUs, synchronous data parallel, one rank per GPU) lost
throughput twice during yesterday's run and never recovered. The on-call engineer saved everything
we have under `/app/telemetry/`:

- `hostfile.txt`: the hosts in launch order (node_rank = line order). Each host runs local ranks
  0-7; global rank = node_rank * 8 + local_rank.
- `env/<host>.env`: the environment each host's workers were launched with.
- `step_times.csv`: per-step, per-rank timings (data loading including host-to-device copies,
  forward, backward, all-reduce wait, total).
- `gpu/<host>.csv`: GPU telemetry sampled every 10 s, indexed by the physical GPU index as
  `nvidia-smi` reports it.
- `nvidia-smi-q/<host>.txt`: `nvidia-smi -q` snapshots taken in the evening, after the job had been
  stopped.
- `rank0.log` and `dmesg/<host>.log`.

Several things went wrong on the cluster that day. Find every hardware problem that causes a
lasting slowdown of the job (there may be more than one), and nothing else. We'll take exactly
those machines out of the pool.

Write `/app/answer.json`:

```json
{
  "incidents": [
    {"host": "<hostname>", "physical_gpu": <int>, "global_rank": <int>,
     "start_step": <int, first step at which this problem slows the job>,
     "cause": "<one of: network, data_loading, thermal, ecc_memory, clock_or_power_throttling, pcie_link_degraded, software>"}
  ],
  "cordon": ["<every host to remove from the pool, and only those>"]
}
```
