"""Small chaos helper for local testing: kills one random Ray worker process after a delay.

    python chaos.py --delay 3        # while pipeline.py is running against the same machine
"""
import argparse
import os
import random
import signal
import subprocess
import time

ap = argparse.ArgumentParser()
ap.add_argument("--delay", type=float, default=3.0)
a = ap.parse_args()
time.sleep(a.delay)
ps = subprocess.run(["ps", "-eo", "pid,args"], capture_output=True, text=True).stdout.splitlines()[1:]
victims = [int(l.split()[0]) for l in ps if l.split(None, 1)[1].startswith("ray::") and "IDLE" not in l]
if victims:
    v = random.choice(victims)
    os.kill(v, signal.SIGKILL)
    print("killed", v)
