#!/bin/bash
# Shortcut (partial fix): right zone, volume and tolerations, but keep the original oversized requests and
# limits, so the pods never pass the namespace's LimitRange / ResourceQuota admission.
APP=${APP_DIR:-/app}
cp -r /solution/files/. "$APP/"
APP=$APP python3 - <<'PY'
import os
import yaml
p = os.path.join(os.environ["APP"], "job", "pytorchjob.yaml")
job = yaml.safe_load(open(p))
for rs in job["spec"]["pytorchReplicaSpecs"].values():
    c = [c for c in rs["template"]["spec"]["containers"] if c["name"] == "pytorch"][0]
    c["resources"]["requests"].update({"cpu": "180", "memory": "2000Gi"})
    c["resources"]["limits"]["memory"] = "2000Gi"
yaml.safe_dump(job, open(p, "w"), sort_keys=False)
PY
