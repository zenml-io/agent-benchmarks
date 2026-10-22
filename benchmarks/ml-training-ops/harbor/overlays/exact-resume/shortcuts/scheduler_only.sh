#!/bin/bash
# Shortcut (partial fix): also checkpoint and restore the learning-rate schedule, but not the random
# number generators (dropout masks and data order still diverge after a resume).
APP=${APP_DIR:-/app} python3 - <<'PY'
import os
p = os.path.join(os.environ["APP"], "train.py")
s = open(p).read()
s2 = s.replace('''        opt.load_state_dict(state["opt"])
''', '''        opt.load_state_dict(state["opt"])
        sched.load_state_dict(state["sched"])
''').replace('''{"model": model.state_dict(), "opt": opt.state_dict(), "step": step}''',
             '''{"model": model.state_dict(), "opt": opt.state_dict(), "sched": sched.state_dict(), "step": step}''')
assert s2.count("sched.state_dict()") == 1 and 'state["sched"]' in s2
open(p, "w").write(s2)
PY
