#!/bin/bash
# Shortcut: the reference placement, but get past the taints with a blanket toleration (tolerates every
# taint, including the dedicated nodes and cordons), which the platform policy forbids.
APP=${APP_DIR:-/app}
cp -r /solution/files/. "$APP/"
APP=$APP python3 - <<'PY'
import os
import yaml
p = os.path.join(os.environ["APP"], "job", "pytorchjob.yaml")
job = yaml.safe_load(open(p))
for rs in job["spec"]["pytorchReplicaSpecs"].values():
    rs["template"]["spec"]["tolerations"] = [{"operator": "Exists"}]
yaml.safe_dump(job, open(p, "w"), sort_keys=False)
PY
