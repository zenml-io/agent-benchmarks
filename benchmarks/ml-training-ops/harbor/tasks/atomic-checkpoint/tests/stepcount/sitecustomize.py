"""Grader instrumentation: when STEPCOUNT_FILE is set, append to that file one line per optimizer step
("<rank> step") and per backward pass ("<rank> backward") of this process, plus "<rank> start" once
loaded. Put this directory on PYTHONPATH of the job under test; workers started by torchrun inherit it."""
import os

if os.environ.get("STEPCOUNT_FILE"):
    import torch
    from torch.optim.optimizer import register_optimizer_step_post_hook

    _path, _rank = os.environ["STEPCOUNT_FILE"], os.environ.get("RANK", "0")

    def _log(kind):
        fd = os.open(_path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
        try:
            os.write(fd, f"{_rank} {kind}\n".encode())
        finally:
            os.close(fd)

    register_optimizer_step_post_hook(lambda opt, args, kwargs: _log("step"))
    _backward = torch.autograd.backward

    def _counted_backward(*args, **kwargs):
        _log("backward")
        return _backward(*args, **kwargs)

    torch.autograd.backward = _counted_backward
    _log("start")  # lets the grader tell "no steps" from "instrumentation not loaded"
