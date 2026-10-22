# Cluster defaults for training jobs on the gpu-l40s pool (maintained by the platform team).
# Sourced by every launcher. Last edited: 2026-09-18.
export NCCL_P2P_DISABLE=1          # no P2P between L40S in this chassis
export NCCL_CUMEM_ENABLE=0
export NCCL_NVLS_ENABLE=0
export NCCL_IB_DISABLE=1
export NCCL_SOCKET_IFNAME=lo,eth0
export OMP_NUM_THREADS=8
export TOKENIZERS_PARALLELISM=false
export HF_DATASETS_OFFLINE=1
export TORCH_NCCL_ASYNC_ERROR_HANDLING=1
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
# long-context sweep (LC-41)
export TITAN_ROPE_THETA=10000
export TITAN_RUN_TAG=pool-l40s
