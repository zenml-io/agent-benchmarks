#!/bin/bash
# Alternative fix: every rank starts from the same seed; each rank backpropagates the *sum* of its
# per-example losses and GradSync divides the summed gradient by the number of examples in the global
# batch, counted with an all_reduce (so it works for any split).
APP=${APP_DIR:-/app} python3 - <<'PY'
import os
app = os.environ["APP"]
p = os.path.join(app, "trainer", "dist_utils.py")
s = open(p).read()
s2 = s.replace('''    def sync(self):
        grads = [p.grad for p in self.params]
        flat = torch.cat([g.reshape(-1) for g in grads])
        dist.all_reduce(flat, op=dist.ReduceOp.SUM)
''', '''    def sync(self, local_examples):
        grads = [p.grad for p in self.params]
        flat = torch.cat([g.reshape(-1) for g in grads] + [torch.tensor([float(local_examples)])])
        dist.all_reduce(flat, op=dist.ReduceOp.SUM)
        flat = flat[:-1] / flat[-1]
''')
assert "local_examples" in s2
open(p, "w").write(s2)
p = os.path.join(app, "train.py")
s = open(p).read()
s2 = s.replace("    seed_everything(cfg.seed, rank)\n", "    seed_everything(cfg.seed, 0)  # identical initial weights on every rank\n").replace(
    "        loss = F.cross_entropy(model(x), y)\n", "        loss = F.cross_entropy(model(x), y, reduction=\"sum\")\n").replace(
    "        sync.sync()\n", "        sync.sync(len(y))\n")
assert "sync.sync(len(y))" in s2 and "seed_everything(cfg.seed, 0)" in s2 and 'reduction="sum"' in s2
open(p, "w").write(s2)
PY
