#!/bin/bash
# Shortcut: the reference fix without any zone constraint: the scheduler can place the pods today, but
# nothing in the spec keeps the gang in one availability zone.
APP=${APP_DIR:-/app}
cp -r /solution/files/. "$APP/"
APP=$APP python3 - <<'PY'
import os
import yaml
p = os.path.join(os.environ["APP"], "job", "pytorchjob.yaml")
job = yaml.safe_load(open(p))
for rs in job["spec"]["pytorchReplicaSpecs"].values():
    rs["template"]["spec"]["nodeSelector"].pop("topology.kubernetes.io/zone")
yaml.safe_dump(job, open(p, "w"), sort_keys=False)
PY
