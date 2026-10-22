import torch
from torch.utils.data import DataLoader, TensorDataset

N, D, K = 8192, 48, 6
BATCH = 64


def dataset():
    g = torch.Generator().manual_seed(11)
    x = torch.randn(N, D, generator=g)
    w = torch.randn(D, K, generator=g)
    y = (x @ w + 0.3 * torch.randn(N, K, generator=g)).argmax(1)
    return TensorDataset(x, y)


def loader(generator):
    """Shuffled every epoch; the order comes from `generator` (one randperm per epoch)."""
    return DataLoader(dataset(), batch_size=BATCH, shuffle=True, generator=generator, drop_last=True)


STEPS_PER_EPOCH = N // BATCH
