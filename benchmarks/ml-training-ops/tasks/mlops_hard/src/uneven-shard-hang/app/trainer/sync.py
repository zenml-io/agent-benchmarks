import torch
import torch.distributed as dist


@torch.no_grad()
def average_gradients(model):
    world = dist.get_world_size()
    for p in model.parameters():
        dist.all_reduce(p.grad, op=dist.ReduceOp.SUM)
        p.grad /= world


@torch.no_grad()
def broadcast_params(model):
    for p in model.parameters():
        dist.broadcast(p, src=0)


def global_mean(value):
    t = torch.tensor([float(value)])
    dist.all_reduce(t, op=dist.ReduceOp.SUM)
    return t.item() / dist.get_world_size()
