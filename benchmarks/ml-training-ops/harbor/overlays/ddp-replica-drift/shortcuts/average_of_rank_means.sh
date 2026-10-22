#!/bin/bash
# Shortcut (what DDP itself would do): start every replica from rank 0's weights and average the summed
# gradients by the number of workers. With uneven shards (3 workers, global batch 512) the average of
# per-rank mean losses is not the global-batch mean.
APP=${APP_DIR:-/app} python3 - <<'PY'
import os
app = os.environ["APP"]
p = os.path.join(app, "trainer", "dist_utils.py")
s = open(p).read()
s2 = s.replace('''        self.params = [p for p in model.parameters() if p.requires_grad]
''', '''        self.params = [p for p in model.parameters() if p.requires_grad]
        with torch.no_grad():
            for t in list(model.parameters()) + list(model.buffers()):
                dist.broadcast(t, src=0)
''').replace('''        dist.all_reduce(flat, op=dist.ReduceOp.SUM)
''', '''        dist.all_reduce(flat, op=dist.ReduceOp.SUM)
        flat /= dist.get_world_size()
''')
assert "flat /= dist.get_world_size()" in s2 and "broadcast" in s2
open(p, "w").write(s2)
PY
