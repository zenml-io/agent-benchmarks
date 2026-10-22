"""Run one fork variant and print timing + losses (debugging the calibration)."""
import os
import sys
import time

import modal

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from calibrate_fork import app, run_variant  # noqa: E402,F401


@app.local_entrypoint()
def one(faults: str = "", steps: int = 50):
    t = time.time()
    f, curve, tail = run_variant.remote(faults, steps)
    print("faults", repr(f), "seconds", round(time.time() - t), "losses", curve[:3], curve[-3:])
    if tail:
        print(tail[-1500:])
