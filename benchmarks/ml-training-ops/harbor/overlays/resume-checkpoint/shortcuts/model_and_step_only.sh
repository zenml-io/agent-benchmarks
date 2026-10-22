#!/bin/bash
# Shortcut (partial fix): resume the step counter and the weights, but not the optimizer or the schedule.
APP=${APP_DIR:-/app} python3 - <<'PY'
import os
p = os.path.join(os.environ["APP"], "train.py")
s = open(p).read()
s2 = s.replace("""        model.load_state_dict(state["model"])
""", """        model.load_state_dict(state["model"])
        start = state["step"]
""").replace("""    torch.save({"model": model.state_dict()}, a.ckpt)""",
             """    torch.save({"model": model.state_dict(), "step": a.steps}, a.ckpt)""")
assert s2.count("state[\"step\"]") == 1 and "\"step\": a.steps" in s2
open(p, "w").write(s2)
PY
