#!/bin/bash
# Alternative fix: the zone, product and pool as a required node affinity, the replica claim in that
# zone, and leaner requests (80 CPUs, 1000Gi, limit 1400Gi) within quota and LimitRange.
APP=${APP_DIR:-/app}
cp -r /solution/files/. "$APP/"
APP=$APP python3 - <<'PY'
import os
import yaml
p = os.path.join(os.environ["APP"], "job", "pytorchjob.yaml")
job = yaml.safe_load(open(p))
for rs in job["spec"]["pytorchReplicaSpecs"].values():
    spec = rs["template"]["spec"]
    sel = spec.pop("nodeSelector")
    spec["affinity"] = {"nodeAffinity": {"requiredDuringSchedulingIgnoredDuringExecution": {"nodeSelectorTerms": [
        {"matchExpressions": [{"key": k, "operator": "In", "values": [v]} for k, v in sel.items()]}]}}}
    c = [c for c in spec["containers"] if c["name"] == "pytorch"][0]
    c["resources"]["requests"].update({"cpu": "80", "memory": "1000Gi"})
    c["resources"]["limits"]["memory"] = "1400Gi"
yaml.safe_dump(job, open(p, "w"), sort_keys=False)
PY
