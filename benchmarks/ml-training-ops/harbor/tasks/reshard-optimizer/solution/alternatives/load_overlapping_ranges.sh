#!/bin/bash
# Alternative fix: each rank computes which source shards overlap its slice of the flat parameter vector
# and copies just those ranges (no full concatenation).
APP=${APP_DIR:-/app} python3 - <<'PY'
import os
p = os.path.join(os.environ["APP"], "trainer", "zero.py")
s = open(p).read()
start = s.index("    def load(self, d):")
new = '''    def load(self, d):
        import glob
        import re
        files = glob.glob(os.path.join(d, "optim-rank*-of-*.pt"))
        src_world = int(re.search(r"-of-(\\d+)\\.pt$", files[0]).group(1))
        src_chunk = math.ceil(self.numel / src_world)
        lo, hi = self.rank * self.chunk, min((self.rank + 1) * self.chunk, self.numel)
        exp_avg, exp_avg_sq, t = torch.zeros(self.chunk), torch.zeros(self.chunk), None
        for r in range(src_world):
            s_lo, s_hi = r * src_chunk, min((r + 1) * src_chunk, self.numel)
            a, b = max(lo, s_lo), min(hi, s_hi)
            if a >= b:
                continue
            st = torch.load(os.path.join(d, f"optim-rank{r}-of-{src_world}.pt"))
            assert st["numel"] == self.numel
            exp_avg[a - lo:b - lo] = st["exp_avg"][a - s_lo:b - s_lo]
            exp_avg_sq[a - lo:b - lo] = st["exp_avg_sq"][a - s_lo:b - s_lo]
            t = st["t"]
        if t is None:  # this rank's slice is all padding
            t = torch.load(os.path.join(d, f"optim-rank0-of-{src_world}.pt"))["t"]
        self.exp_avg, self.exp_avg_sq, self.t = exp_avg, exp_avg_sq, t
'''
open(p, "w").write(s[:start] + new)
PY
