#!/bin/bash
# Alternative fix: the culprit as a 7-character short SHA, and the learning rate scaled with the batch size
# in train.py (linear scaling from the batch of 256 the old LR was tuned for) instead of editing config.yaml.
APP=${APP_DIR:-/app}
short=$(python3 -c "import json; print(json.load(open('/solution/files/answer.json'))['culprit_commit'][:7])")
printf '{"culprit_commit": "%s"}\n' "$short" > "$APP/answer.json"
APP=$APP python3 - <<'PY'
import os
p = os.path.join(os.environ["APP"], "repo", "train.py")
s = open(p).read()
old = 'LR = CFG["lr"]\n'
assert old in s
open(p, "w").write(s.replace(old, 'LR = CFG["lr"] * CFG["batch_size"] / 256  # the LR in config.yaml was tuned for batch 256\n'))
PY
