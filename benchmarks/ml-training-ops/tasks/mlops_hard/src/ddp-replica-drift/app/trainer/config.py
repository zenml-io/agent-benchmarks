from dataclasses import dataclass


@dataclass
class Config:
    seed: int = 17
    global_batch: int = 512
    lr: float = 0.05
    momentum: float = 0.9
    weight_decay: float = 1e-4
    d_in: int = 64
    d_hidden: int = 256
    n_classes: int = 10
    log_every: int = 25
