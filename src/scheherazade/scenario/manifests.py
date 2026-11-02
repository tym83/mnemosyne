"""Builders of the Kubernetes objects a simulated cluster consists of.

They are plain dicts in the shape the API server accepts, so the same state
can later be applied to a real cluster unchanged.
"""

from __future__ import annotations

PORTS = {"web": 8080, "api": 8080, "worker": 9090, "cache": 6379, "db": 5432}
IMAGES = {
    "web": "ghcr.io/example/{name}",
    "api": "ghcr.io/example/{name}",
    "worker": "ghcr.io/example/{name}",
    "cache": "docker.io/library/redis",
    "db": "docker.io/library/postgres",
}
BASE_TAG = {"cache": "7.2.4", "db": "16.3"}


def namespace(name: str, labels: dict | None = None) -> dict:
    return {
        "apiVersion": "v1",
        "kind": "Namespace",
        "metadata": {"name": name, "labels": {"kubernetes.io/metadata.name": name, **(labels or {})}},
    }


def image(svc: dict, tag: str) -> str:
    return IMAGES[svc["kind"]].format(name=svc["name"]) + ":" + tag


def workload(ns: str, svc: dict, tag: str, replicas: int) -> dict:
    labels = {"app.kubernetes.io/name": svc["name"], "app.kubernetes.io/component": svc["kind"]}
    container = {
        "name": svc["name"],
        "image": image(svc, tag),
        "ports": [{"containerPort": PORTS[svc["kind"]]}],
        "resources": {
            "requests": {"cpu": "250m" if svc["kind"] != "db" else "1", "memory": "256Mi" if svc["kind"] != "db" else "2Gi"},
        },
    }
    if svc["kind"] in ("web", "api"):
        container["readinessProbe"] = {"httpGet": {"path": "/healthz", "port": PORTS[svc["kind"]]}}
    kind = "StatefulSet" if svc["kind"] in ("db", "cache") else "Deployment"
    spec = {
        "replicas": replicas,
        "selector": {"matchLabels": {"app.kubernetes.io/name": svc["name"]}},
        "template": {"metadata": {"labels": labels}, "spec": {"containers": [container]}},
    }
    if kind == "StatefulSet":
        spec["serviceName"] = svc["name"]
    return {
        "apiVersion": "apps/v1",
        "kind": kind,
        "metadata": {"name": svc["name"], "namespace": ns, "labels": labels},
        "spec": spec,
    }


def service(ns: str, svc: dict) -> dict:
    return {
        "apiVersion": "v1",
        "kind": "Service",
        "metadata": {"name": svc["name"], "namespace": ns},
        "spec": {
            "selector": {"app.kubernetes.io/name": svc["name"]},
            "ports": [{"port": PORTS[svc["kind"]], "targetPort": PORTS[svc["kind"]]}],
        },
    }


def hpa(ns: str, svc: dict, base: int) -> dict:
    return {
        "apiVersion": "autoscaling/v2",
        "kind": "HorizontalPodAutoscaler",
        "metadata": {"name": svc["name"], "namespace": ns},
        "spec": {
            "scaleTargetRef": {"apiVersion": "apps/v1", "kind": "Deployment", "name": svc["name"]},
            "minReplicas": base,
            "maxReplicas": base * 6,
            "metrics": [{"type": "Resource", "resource": {"name": "cpu", "target": {"type": "Utilization", "averageUtilization": 70}}}],
        },
    }


def config(ns: str, svc: dict, data: dict) -> dict:
    return {
        "apiVersion": "v1",
        "kind": "ConfigMap",
        "metadata": {"name": svc["name"] + "-config", "namespace": ns},
        "data": data,
    }


def cronjob(ns: str, name: str, schedule: str, tag: str) -> dict:
    return {
        "apiVersion": "batch/v1",
        "kind": "CronJob",
        "metadata": {"name": name, "namespace": ns},
        "spec": {
            "schedule": schedule,
            "jobTemplate": {"spec": {"template": {"spec": {
                "restartPolicy": "OnFailure",
                "containers": [{"name": name, "image": f"ghcr.io/example/{name}:{tag}"}],
            }}}},
        },
    }


def default_deny(ns: str) -> dict:
    return {
        "apiVersion": "networking.k8s.io/v1",
        "kind": "NetworkPolicy",
        "metadata": {"name": "default-deny", "namespace": ns},
        "spec": {"podSelector": {}, "policyTypes": ["Ingress"]},
    }


def allow_from(ns: str, target: str, sources: list[str], port: int) -> dict:
    return {
        "apiVersion": "networking.k8s.io/v1",
        "kind": "NetworkPolicy",
        "metadata": {"name": f"allow-to-{target}", "namespace": ns},
        "spec": {
            "podSelector": {"matchLabels": {"app.kubernetes.io/name": target}},
            "policyTypes": ["Ingress"],
            "ingress": [{
                "from": [{"podSelector": {"matchLabels": {"app.kubernetes.io/name": s}}} for s in sorted(sources)],
                "ports": [{"port": port}],
            }],
        },
    }


def ingress(ns: str, host: str, svc: dict) -> dict:
    return {
        "apiVersion": "networking.k8s.io/v1",
        "kind": "Ingress",
        "metadata": {"name": svc["name"], "namespace": ns},
        "spec": {"rules": [{"host": host, "http": {"paths": [{
            "path": "/", "pathType": "Prefix",
            "backend": {"service": {"name": svc["name"], "port": {"number": PORTS[svc["kind"]]}}},
        }]}}]},
    }


def node(name: str, region: str, zone: str, version: str) -> dict:
    return {
        "apiVersion": "v1",
        "kind": "Node",
        "metadata": {"name": name, "labels": {
            "topology.kubernetes.io/region": region,
            "topology.kubernetes.io/zone": zone,
            "node.kubernetes.io/kubelet-version": "v" + version,
        }},
    }
