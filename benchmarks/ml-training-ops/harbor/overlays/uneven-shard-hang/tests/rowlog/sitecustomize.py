"""Grader instrumentation: when ROWLOG_DIR is set, record which input rows of width ROWLOG_DIM this
process feeds to a model while gradients are enabled (training, not evaluation), as a count per row
hash, written to <ROWLOG_DIR>/rows-<pid>.json at exit. Put this directory on PYTHONPATH of the job."""
import os

if os.environ.get("ROWLOG_DIR"):
    import atexit
    import collections
    import hashlib
    import json

    import torch
    import torch.nn.modules.module as _module

    _dim = int(os.environ.get("ROWLOG_DIM", "48"))
    _counts = collections.Counter()
    _last = [None]

    def _hook(module, args):
        x = args[0] if args else None
        if not isinstance(x, torch.Tensor) or x.dim() != 2 or x.shape[1] != _dim or not torch.is_grad_enabled():
            return
        if _last[0] is x:  # the same batch passed down to the first layer
            return
        _last[0] = x
        a = x.detach().to(torch.float32).contiguous().numpy()
        for row in a:
            _counts[hashlib.blake2b(row.tobytes(), digest_size=8).hexdigest()] += 1

    _module.register_module_forward_pre_hook(_hook)

    @atexit.register
    def _dump():
        with open(os.path.join(os.environ["ROWLOG_DIR"], f"rows-{os.getpid()}.json"), "w") as f:
            json.dump(_counts, f)
