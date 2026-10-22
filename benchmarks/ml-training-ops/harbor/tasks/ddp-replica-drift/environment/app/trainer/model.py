import torch.nn as nn


def build_model(cfg):
    return nn.Sequential(
        nn.Linear(cfg.d_in, cfg.d_hidden), nn.LayerNorm(cfg.d_hidden), nn.GELU(),
        nn.Linear(cfg.d_hidden, cfg.d_hidden), nn.GELU(),
        nn.Linear(cfg.d_hidden, cfg.n_classes),
    )
