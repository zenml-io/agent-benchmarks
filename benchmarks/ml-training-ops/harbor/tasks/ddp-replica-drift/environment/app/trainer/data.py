"""Synthetic data pipeline.

Every step has a fixed *global* batch (a function of the seed and the step only), so runs are
reproducible regardless of the number of workers. Rank r of W takes rows r, r+W, r+2W, ...
"""
import torch

_TEACHER = None


def _teacher(d_in, n_classes):
    global _TEACHER
    if _TEACHER is None:
        g = torch.Generator().manual_seed(2024)
        _TEACHER = (torch.randn(d_in, 128, generator=g), torch.randn(128, n_classes, generator=g))
    return _TEACHER


def global_batch(cfg, step):
    g = torch.Generator().manual_seed(cfg.seed * 1_000_003 + step)
    x = torch.randn(cfg.global_batch, cfg.d_in, generator=g)
    w1, w2 = _teacher(cfg.d_in, cfg.n_classes)
    y = (torch.tanh(x @ w1) @ w2).argmax(1)
    return x, y


def shard(x, y, rank, world):
    return x[rank::world], y[rank::world]


def eval_set(cfg, n=4096):
    cfg_eval = type(cfg)(**{**cfg.__dict__, "seed": cfg.seed + 99991, "global_batch": n})
    return global_batch(cfg_eval, 0)
