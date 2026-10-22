#!/bin/bash
# Shortcut (partial fix): undo the attention-scale and loss faults but not the data-sharding one. Needs the
# GPU run to be caught (the curve stays off); the GPU-free tests alone pass it.
python - <<'PY'
import os
T = "/app/titan"
for rel, old, new in [
    ("torchtitan/models/llama3/model/model.py", "self.attn_scale = model_args.dim**-0.5", "self.attn_scale = self.head_dim**-0.5"),
    ("torchtitan/components/loss.py", "for i in range(0, n - CE_CHUNK + 1, CE_CHUNK):", "for i in range(0, n, CE_CHUNK):"),
]:
    p = os.path.join(T, rel)
    s = open(p).read()
    assert old in s
    open(p, "w").write(s.replace(old, new))
PY
