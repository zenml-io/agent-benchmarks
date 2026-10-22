import torch


def make_data(n, seed, d=32, k=4):
    """Synthetic classification data from a fixed random teacher (the same for every seed)."""
    teacher = torch.Generator().manual_seed(1234)
    W = torch.randn(d, k, generator=teacher)
    g = torch.Generator().manual_seed(seed)
    X = torch.randn(n, d, generator=g)
    y = (X @ W + 0.5 * torch.tanh(X[:, :k])).argmax(1)
    return X, y
