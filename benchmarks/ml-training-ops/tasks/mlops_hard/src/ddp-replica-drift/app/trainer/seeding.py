import random

import numpy as np
import torch


def seed_everything(base_seed, rank):
    """Per-rank seeds so that any randomness (augmentation, dropout) differs across ranks."""
    s = base_seed + rank
    random.seed(s)
    np.random.seed(s)
    torch.manual_seed(s)
