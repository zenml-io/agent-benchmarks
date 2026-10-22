"""Generate the telemetry of a 64-GPU synchronous training run with one degraded GPU and several decoys."""
import os

import numpy as np

rng = np.random.default_rng(20261008)
HOSTS = ["gpu-a03", "gpu-a07", "gpu-a11", "gpu-b02", "gpu-b05", "gpu-b09", "gpu-b14", "gpu-c01"]
ORDER = [3, 6, 0, 7, 1, 5, 2, 4]  # hostfile order (rank blocks)
CVD = {h: "0,1,2,3,4,5,6,7" for h in HOSTS}
CVD["gpu-b09"] = "0,1,2,3,7,6,5,4"   # topology-aware ordering on the newer chassis
CVD["gpu-b14"] = "0,1,2,3,7,6,5,4"
BAD_HOST, BAD_GPU, BAD_STEP = "gpu-b09", 6, 1812
B2_HOST, B2_GPU, B2_STEP = "gpu-a03", 2, 2407  # PCIe link trained down to x8: host-to-device copies slow
HOT_HOST = "gpu-b05"                 # decoy: hot rack position, clocks fine
ECC_HOST, ECC_GPU = "gpu-a07", 5     # decoy: rising correctable ECC errors
STEPS = 3000
os.makedirs("telemetry/gpu", exist_ok=True)
os.makedirs("telemetry/env", exist_ok=True)
os.makedirs("telemetry/dmesg", exist_ok=True)

ranks = []  # (rank, host, local_rank, physical_gpu)
for i, hi in enumerate(ORDER):
    h = HOSTS[hi]
    phys = [int(c) for c in CVD[h].split(",")]
    for lr in range(8):
        ranks.append((i * 8 + lr, h, lr, phys[lr]))
with open("telemetry/hostfile.txt", "w") as f:
    f.write("# torchrun --nnodes=8 --nproc_per_node=8; node_rank = line number (0-based)\n")
    for hi in ORDER:
        f.write(f"{HOSTS[hi]} slots=8\n")
for h in HOSTS:
    with open(f"telemetry/env/{h}.env", "w") as f:
        f.write(f"HOSTNAME={h}\nCUDA_VISIBLE_DEVICES={CVD[h]}\nNCCL_IB_HCA=mlx5\nNCCL_SOCKET_IFNAME=ens\nOMP_NUM_THREADS=8\n")

R = len(ranks)
bad_rank = next(r for r, h, lr, g in ranks if h == BAD_HOST and g == BAD_GPU)
steps = np.arange(STEPS)
fwd = rng.normal(262, 3.0, (STEPS, R))
bwd = rng.normal(548, 5.0, (STEPS, R))
slow = steps >= BAD_STEP
ramp = np.clip((steps - BAD_STEP) / 15.0, 0, 1)  # brake engages over ~15 steps
fwd[:, bad_rank] *= 1 + 0.36 * ramp
bwd[:, bad_rank] *= 1 + 0.36 * ramp
load = np.abs(rng.normal(14, 2.0, (STEPS, R)))
for r, h, lr, g in ranks:  # decoy: one rank's dataloader stalls at checkpoint steps
    if h == "gpu-a11" and lr == 1:
        load[steps % 250 == 0, r] += rng.uniform(1500, 2600, (steps % 250 == 0).sum())
b2_rank = next(r for r, h, lr, g in ranks if h == B2_HOST and g == B2_GPU)
load[steps >= B2_STEP, b2_rank] += rng.normal(430, 15, (steps >= B2_STEP).sum())
ckpt = steps % 250 == 0
compute = load + fwd + bwd
slowest = compute.max(1, keepdims=True)
comm = rng.normal(205, 6.0, (STEPS, R))
rackb = np.array([h.startswith("gpu-b") for _, h, _, _ in ranks])
net = (steps >= 905) & (steps < 1010)  # decoy: transient congestion on rack b uplink
comm[np.ix_(net, rackb)] += rng.uniform(250, 420, (net.sum(), rackb.sum()))
comm[net] = comm[net].max(1, keepdims=True) + rng.normal(0, 4, (net.sum(), R))  # all-reduce waits for the slowest link
allreduce = comm + (slowest - compute)
step_ms = load + fwd + bwd + allreduce
with open("telemetry/step_times.csv", "w") as f:
    f.write("step,rank,dataload_ms,fwd_ms,bwd_ms,allreduce_ms,step_ms\n")
    for s in range(STEPS):
        for r in range(R):
            f.write(f"{s},{r},{load[s, r]:.1f},{fwd[s, r]:.1f},{bwd[s, r]:.1f},{allreduce[s, r]:.1f},{step_ms[s, r]:.1f}\n")

# wall clock per step (same on all ranks), for GPU telemetry timestamps
t_step = step_ms.mean(1) / 1000.0
t = np.concatenate([[0], np.cumsum(t_step)])
T0 = 1759910400  # 2025-10-08T08:00:00Z
dur = t[-1]
for h in HOSTS:
    with open(f"telemetry/gpu/{h}.csv", "w") as f:
        f.write("timestamp,gpu,sm_clock_mhz,mem_clock_mhz,power_w,temp_c,util_pct,ecc_sbe_total,ecc_dbe_total,xid\n")
        sbe = np.zeros(8)
        for ts in np.arange(0, dur, 10.0):
            s = min(int(np.searchsorted(t, ts)), STEPS - 1)
            for g in range(8):
                clock, power = rng.normal(1980, 4), rng.normal(688, 9)
                temp = rng.normal(64, 1.5) + (19 if h == HOT_HOST else 0)
                util = rng.normal(97, 1.2)
                if h == BAD_HOST and g == BAD_GPU and s >= BAD_STEP:
                    clock, power, temp = rng.normal(1410, 15), rng.normal(468, 12), rng.normal(58, 1.5)
                elif h == B2_HOST and g == B2_GPU and s >= B2_STEP:
                    util, power = rng.normal(61, 3), rng.normal(512, 15)  # starved by slow host-to-device copies
                elif s >= BAD_STEP:
                    util = rng.normal(79, 2.5)  # everyone else waits for the slow GPU
                if h == ECC_HOST and g == ECC_GPU:
                    sbe[g] += rng.poisson(3)
                f.write(f"{int(T0 + ts)},{g},{clock:.0f},2619,{power:.0f},{temp:.0f},{min(util, 100):.0f},{int(sbe[g])},0,0\n")

with open("telemetry/rank0.log", "w") as f:
    for s in range(STEPS):
        if s % 10 == 0:
            tok = 512 * 4096 * 64 / (step_ms[s].mean() / 1000)
            f.write(f"[{T0 + t[s]:.0f}] step {s} loss {2.9 * np.exp(-s / 1400) + 1.6 + rng.normal(0, .01):.4f} "
                    f"step_time {step_ms[s].mean():.0f}ms tokens/s {tok:,.0f}\n")
        if ckpt[s] and s:
            f.write(f"[{T0 + t[s]:.0f}] saved checkpoint step {s} to s3://train-ckpt/run-1008/step_{s:06d}\n")
        if net[s] and s == 905:
            f.write(f"[{T0 + t[s]:.0f}] WARNING NCCL watchdog: collective took 612ms (> 500ms)\n")

for h in HOSTS:
    with open(f"telemetry/dmesg/{h}.log", "w") as f:
        f.write(f"[    0.000000] Linux version 6.8.0-1015-nvidia ({h})\n")
        f.write("[   12.381022] nvidia: loading out-of-tree module taints kernel.\n")
        f.write("[   14.902114] NVRM: loading NVIDIA UNIX x86_64 Kernel Module  560.35.03\n")
        if h == ECC_HOST:
            for k in range(6):
                f.write(f"[{8000 + 900 * k:>11.6f}] NVRM: GPU at PCI:0000:{0x9a + ECC_GPU:02x}:00: GPU-6b1e... "
                        f"corrected memory error (single-bit), page retired: no\n")
        if h.startswith("gpu-b"):
            f.write(f"[{11800.0 + HOSTS.index(h):>11.6f}] mlx5_core 0000:1a:00.0 ens1: Link up, 400Gbps, (after flap)\n")
        if h == HOT_HOST:
            f.write("[ 9800.120000] ipmi: fan 3 speed below threshold, raised to 100%\n")
os.makedirs("telemetry/nvidia-smi-q", exist_ok=True)
for h in HOSTS:  # snapshots taken at 20:40, after the job was stopped (GPUs idle)
    with open(f"telemetry/nvidia-smi-q/{h}.txt", "w") as f:
        f.write(f"==============NVSMI LOG==============\nTimestamp : Wed Oct  8 20:40:12 2025\nDriver Version : 560.35.03\nCUDA Version : 12.6\nAttached GPUs : 8\n")
        for g in range(8):
            width = "8x" if (h == B2_HOST and g == B2_GPU) else "16x"
            f.write(f"""
GPU 00000000:{0x18 + 0x10 * g:02X}:00.0
    Product Name : NVIDIA H100 80GB HBM3
    Serial Number : 1654{HOSTS.index(h):02d}{g:02d}0{(sum(map(ord, h)) * 37 % 9000) + 1000}
    GPU Link Info
        PCIe Generation
            Max : 5
            Current : 1
            Device Current : 1
            Device Max : 5
            Host Max : 5
        Link Width
            Max : 16x
            Current : {width}
    Clocks Event Reasons
        Idle : Active
        HW Slowdown : Not Active
        HW Power Brake Slowdown : Not Active
        SW Thermal Slowdown : Not Active
    Performance State : P8
    Temperature
        GPU Current Temp : {31 + g % 3} C
    Power Readings
        Power Draw : {68 + g} W
    ECC Errors
        Volatile
            SRAM Correctable : {37 if (h == ECC_HOST and g == ECC_GPU) else 0}
            SRAM Uncorrectable : 0
""")
print("bad ranks", bad_rank, b2_rank)
