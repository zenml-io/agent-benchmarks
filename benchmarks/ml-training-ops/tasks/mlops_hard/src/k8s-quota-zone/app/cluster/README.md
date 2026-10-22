Snapshot of the cluster taken 2026-10-10 06:10 UTC by the on-call (no kubectl access from here):

- nodes.yaml        `kubectl get nodes -o yaml`
- storage.yaml      `kubectl get pvc,pv -n training -o yaml`
- namespace-limits.yaml  `kubectl get resourcequota,limitrange -n training -o yaml`
- pods.yaml         `kubectl get pods -A -o yaml` (running pods only, trimmed to the scheduling-relevant fields)
- describe-pod.txt  `kubectl describe pod` of the pending master

Cluster policy (platform team):
- nodes labelled pool=inference or pool=research, and their `dedicated=...` taints, belong to other teams.
  Training jobs must never tolerate `dedicated` taints, and must not use blanket tolerations
  (a toleration with no key and operator Exists).
- multi-node training jobs must run inside a single availability zone (EFA does not cross zones).
- cordoned nodes are cordoned for a reason.
