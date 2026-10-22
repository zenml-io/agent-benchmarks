#!/bin/bash
# Alternative fix: keep the model checkpoint as it was and save the training state (optimizer, schedule,
# step) to a second file next to it; the step comes back from the scheduler's own counter.
APP=${APP_DIR:-/app} python3 - <<'PY'
import os
p = os.path.join(os.environ["APP"], "train.py")
s = open(p).read()
s2 = s.replace("""        model.load_state_dict(state["model"])
""", """        model.load_state_dict(state["model"])
        extra = torch.load(a.ckpt + ".train_state")
        opt.load_state_dict(extra["optimizer"])
        sched.load_state_dict(extra["scheduler"])
        start = sched.last_epoch
""").replace("""    torch.save({"model": model.state_dict()}, a.ckpt)""",
             """    torch.save({"model": model.state_dict()}, a.ckpt)
    torch.save({"optimizer": opt.state_dict(), "scheduler": sched.state_dict()}, a.ckpt + ".train_state")""")
assert "train_state" in s2 and "sched.last_epoch" in s2
open(p, "w").write(s2)
PY
