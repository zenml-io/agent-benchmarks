#!/bin/bash
# Alternative fix: drop the augmentation memo and recompute the (deterministic) augmentation for the step
# within the epoch, keep only the newest CAPACITY replay rows as a fresh tensor, and log Python floats.
APP=${APP_DIR:-/app} python3 - <<'PY'
import os
app = os.environ["APP"]
p = os.path.join(app, "trainer", "data.py")
s = open(p).read()
old = """        key = (step, x.shape[0])  # same step -> same augmentation
        if key not in self._memo:
            g = torch.Generator().manual_seed(self.seed * 7919 + step)
            noise = torch.randn(x.shape, generator=g) * 0.05
            self._memo[key] = x + noise + 0.1 * torch.roll(x, 1, 0)
        return self._memo[key]"""
assert old in s
open(p, "w").write(s.replace(old, """        g = torch.Generator().manual_seed(self.seed * 7919 + step)  # deterministic: no memo needed
        noise = torch.randn(x.shape, generator=g) * 0.05
        return x + noise + 0.1 * torch.roll(x, 1, 0)"""))
p = os.path.join(app, "trainer", "replay.py")
s = open(p).read()
old = "        x_keep, y_keep = self.x[-self.CAPACITY:], self.y[-self.CAPACITY:]  # drop the oldest\n"
assert old in s
open(p, "w").write(s.replace(old, """        if len(self.y) > self.CAPACITY:  # drop the oldest; copy so the old storage is freed
            self.x = self.x[len(self.y) - self.CAPACITY:].contiguous().clone()
            self.y = self.y[len(self.y) - self.CAPACITY:].clone()
"""))
p = os.path.join(app, "train.py")
s = open(p).read()
s2 = s.replace("        x = aug(step, x)\n", "        x = aug(step % STEPS_PER_EPOCH, x)\n").replace(
    "        hist.log(loss, gn)\n", "        hist.log(float(loss), float(gn))\n")
assert "STEPS_PER_EPOCH, x)" in s2 and "float(loss)" in s2
open(p, "w").write(s2)
PY
