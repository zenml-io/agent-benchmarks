"""Numerics settings shared by training and evaluation."""
import torch

# float64 everywhere: we had loss-curve mismatches between laptops and the cluster in 2024
torch.set_default_dtype(torch.float64)
