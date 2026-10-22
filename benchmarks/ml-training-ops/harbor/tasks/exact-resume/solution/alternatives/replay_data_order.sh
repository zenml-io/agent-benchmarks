#!/bin/bash
# Alternative fix: instead of saving the data generator's state, rebuild it on resume by replaying the
# shuffles of the epochs already done; save and restore the schedule and the global RNG (dropout).
APP=${APP_DIR:-/app} python3 - <<'PY'
import os
p = os.path.join(os.environ["APP"], "train.py")
s = open(p).read()
s2 = s.replace('''        opt.load_state_dict(state["opt"])
        step = state["step"]
''', '''        opt.load_state_dict(state["opt"])
        sched.load_state_dict(state["sched"])
        step = state["step"]
        for _ in range(step // STEPS_PER_EPOCH):  # replay finished epochs' shuffles (same generator draws)
            for _batch in dl:
                pass
        rng_after_save = state["rng"]
''').replace('''    start_epoch, skip = divmod(step, STEPS_PER_EPOCH)
''', '''    start_epoch, skip = divmod(step, STEPS_PER_EPOCH)
    resumed_rng = rng_after_save if path else None
''').replace('''            if epoch == start_epoch and i < skip:
                continue
''', '''            if epoch == start_epoch and i < skip:
                continue
            if resumed_rng is not None:  # dropout continues where the checkpoint left off
                torch.set_rng_state(resumed_rng)
                resumed_rng = None
''').replace('''{"model": model.state_dict(), "opt": opt.state_dict(), "step": step}''',
             '''{"model": model.state_dict(), "opt": opt.state_dict(), "sched": sched.state_dict(), "step": step,
                           "rng": torch.get_rng_state()}''')
assert "rng_after_save" in s2 and "resumed_rng = None" in s2 and '"rng": torch.get_rng_state()' in s2
open(p, "w").write(s2)
PY
