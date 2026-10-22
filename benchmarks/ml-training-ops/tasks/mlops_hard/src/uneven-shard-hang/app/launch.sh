#!/bin/bash
# launch the nightly job (things we tried while debugging the hang are left commented in)
export GLOO_SOCKET_IFNAME=lo
# export GLOO_SOCKET_IFNAME=eth0
export TORCH_DISTRIBUTED_DEBUG=OFF
# export TORCH_GLOO_LAZY_INIT=1
# export NCCL_P2P_DISABLE=1   # (not used with gloo, from the GPU cluster template)
NPROC=${NPROC:-3}
N_TRAIN=${N_TRAIN:-19970}
torchrun --standalone --nproc_per_node=$NPROC /app/train.py --n-train $N_TRAIN --epochs 3 --out /app/out
