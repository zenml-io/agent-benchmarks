"""Writes app/cluster/{nodes.yaml,pods.yaml} (kubectl -o yaml style). Run once; outputs are committed."""
import yaml

NODES = []
spec = {  # name: (zone, pool, extra taints, unschedulable, ready)
    "gpu-a-1": ("us-east-1a", "training", [], False, True),
    "gpu-a-2": ("us-east-1a", "training", [], False, True),
    "gpu-a-3": ("us-east-1a", "training", [], False, True),
    "gpu-a-4": ("us-east-1a", "training", [], False, True),
    "gpu-b-1": ("us-east-1b", "training", [], False, True),
    "gpu-b-2": ("us-east-1b", "training", [], False, True),
    "gpu-b-3": ("us-east-1b", "training", [], True, True),
    "gpu-b-4": ("us-east-1b", "training", [], False, True),
    "gpu-b-5": ("us-east-1b", "inference", [{"key": "dedicated", "value": "inference", "effect": "NoSchedule"}], False, True),
    "gpu-b-6": ("us-east-1b", "training", [], False, True),
    "gpu-c-1": ("us-east-1c", "research", [{"key": "dedicated", "value": "research", "effect": "NoSchedule"}], False, True),
    "gpu-c-2": ("us-east-1c", "research", [{"key": "dedicated", "value": "research", "effect": "NoSchedule"}], False, True),
    "gpu-c-3": ("us-east-1c", "research", [{"key": "dedicated", "value": "research", "effect": "NoSchedule"}], False, True),
}
for i, (name, (zone, pool, taints, unsched, ready)) in enumerate(spec.items()):
    alloc = {"cpu": "190", "memory": "1952Gi", "ephemeral-storage": "3400Gi", "nvidia.com/gpu": "8",
             "vpc.amazonaws.com/efa": "32", "hugepages-2Mi": "0", "pods": "110"}
    n = {"apiVersion": "v1", "kind": "Node",
         "metadata": {"name": name, "labels": {
             "kubernetes.io/hostname": name, "kubernetes.io/os": "linux", "kubernetes.io/arch": "amd64",
             "node.kubernetes.io/instance-type": "p5.48xlarge", "topology.kubernetes.io/region": "us-east-1",
             "topology.kubernetes.io/zone": zone, "pool": pool,
             "nvidia.com/gpu.product": "NVIDIA-H100-80GB-HBM3", "nvidia.com/gpu.count": "8",
             "nvidia.com/gpu.memory": "81559", "nvidia.com/cuda.driver.major": "560",
             "eks.amazonaws.com/nodegroup": f"p5-{pool}-{zone[-1]}", "efa.capable": "true"},
             "annotations": {"node.alpha.kubernetes.io/ttl": "0", "volumes.kubernetes.io/controller-managed-attach-detach": "true"}},
         "spec": {"providerID": f"aws:///{zone}/i-0{(i * 7919 + 104729) * 99991:015x}",
                  "taints": [{"key": "nvidia.com/gpu", "value": "present", "effect": "NoSchedule"}] + taints},
         "status": {"capacity": {**alloc, "memory": "2063Gi", "cpu": "192"}, "allocatable": alloc,
                    "conditions": [
                        {"type": "MemoryPressure", "status": "False", "reason": "KubeletHasSufficientMemory"},
                        {"type": "DiskPressure", "status": "False", "reason": "KubeletHasNoDiskPressure"},
                        {"type": "PIDPressure", "status": "False", "reason": "KubeletHasSufficientPID"},
                        {"type": "Ready", "status": "True" if ready else "False", "reason": "KubeletReady"}],
                    "nodeInfo": {"kubeletVersion": "v1.30.4-eks-a737599", "containerRuntimeVersion": "containerd://1.7.22",
                                 "osImage": "Amazon Linux 2023.5.20240916", "kernelVersion": "6.1.109-118.189.amzn2023.x86_64"}}}
    if unsched:
        n["spec"]["unschedulable"] = True
        n["spec"]["taints"].append({"key": "node.kubernetes.io/unschedulable", "effect": "NoSchedule"})
    NODES.append(n)
yaml.safe_dump({"apiVersion": "v1", "kind": "List", "items": NODES}, open("app/cluster/nodes.yaml", "w"), sort_keys=False)

PODS = []


def pod(name, node, gpu, mem, cpu, ns="training"):
    PODS.append({"apiVersion": "v1", "kind": "Pod", "metadata": {"name": name, "namespace": ns},
                 "spec": {"nodeName": node, "containers": [{"name": "main", "resources": {
                     "requests": {"cpu": cpu, "memory": mem, "nvidia.com/gpu": str(gpu)},
                     "limits": {"memory": mem, "nvidia.com/gpu": str(gpu)}}}]},
                 "status": {"phase": "Running"}})


pod("llm-sft-0911-master-0", "gpu-a-1", 8, "1400Gi", "160")
pod("llm-sft-0911-worker-0", "gpu-a-2", 8, "1400Gi", "160")
pod("embed-eval-7f9c-0", "gpu-a-3", 4, "600Gi", "64", ns="eval")
pod("vllm-serve-qwen-5d8b", "gpu-b-5", 8, "900Gi", "96", ns="inference")
pod("notebook-dev-0", "gpu-b-4", 0, "64Gi", "16", ns="research")
pod("research-sweep-12", "gpu-c-1", 8, "1200Gi", "128", ns="research")
for i, n in enumerate(spec):  # daemonsets everywhere
    pod(f"nvidia-device-plugin-{i:02d}", n, 0, "512Mi", "100m", ns="kube-system")
    pod(f"aws-efa-k8s-device-plugin-{i:02d}", n, 0, "256Mi", "100m", ns="kube-system")
    pod(f"node-exporter-{i:02d}", n, 0, "180Mi", "100m", ns="monitoring")
yaml.safe_dump({"apiVersion": "v1", "kind": "List", "items": PODS}, open("app/cluster/pods.yaml", "w"), sort_keys=False)
