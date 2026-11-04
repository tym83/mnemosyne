"""Manifests of a simulated cluster at a moment, ready for a real cluster.

    python hack/restore/state_manifests.py shop 2025-07-01T00:00:00+00:00 > shop-2025-07-01.yaml

The state is the replay of the year's history up to the moment. Nodes
become KWOK nodes (fake kubelets), so workloads schedule without real
machines; everything else is applied as it was, namespaces first.
"""
import json
import sys
from datetime import datetime
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from mnemosyne.architecture import state_at  # noqa: E402

ORDER = ["Namespace", "ConfigMap", "Service", "Deployment", "StatefulSet", "CronJob",
         "HorizontalPodAutoscaler", "NetworkPolicy", "Ingress"]


def main():
    cluster, at = sys.argv[1], datetime.fromisoformat(sys.argv[2])
    objs = state_at(Path("out/scenarios") / cluster / "ops.jsonl", at)
    docs = []
    for kind in ORDER:
        for (k, ns, name), o in sorted(objs.items()):
            if k == kind:
                docs.append(o)
    for (k, ns, name), o in sorted(objs.items()):
        if k == "Node":
            n = json.loads(json.dumps(o))
            n["metadata"].setdefault("annotations", {})["kwok.x-k8s.io/node"] = "fake"
            n["metadata"]["labels"]["type"] = "kwok"
            n["spec"] = {"taints": [{"key": "kwok.x-k8s.io/node", "value": "fake", "effect": "NoSchedule"}]}
            docs.insert(0, n)
    # Workloads must tolerate the fake nodes.
    for d in docs:
        if d["kind"] in ("Deployment", "StatefulSet"):
            d["spec"]["template"]["spec"]["tolerations"] = [{"key": "kwok.x-k8s.io/node", "operator": "Exists", "effect": "NoSchedule"}]
            d["spec"]["template"]["spec"]["nodeSelector"] = {"type": "kwok"}
    yaml.safe_dump_all(docs, sys.stdout, sort_keys=False)
    print(f"# {len(docs)} objects of {cluster} at {at.isoformat()}", file=sys.stderr)


if __name__ == "__main__":
    main()
