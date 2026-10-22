#!/bin/bash
# Alternative fix: the same placement expressed as a required node affinity instead of a nodeSelector,
# with the minimum requests the job needs (160 CPUs, 1600Gi).
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
    c["resources"]["requests"].update({"cpu": "160", "memory": "1600Gi"})
    c["resources"]["limits"]["memory"] = "1600Gi"
yaml.safe_dump(job, open(p, "w"), sort_keys=False)
PY
