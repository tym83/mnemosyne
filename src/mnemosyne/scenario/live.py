"""A scenario lived by a real cluster: its year of operations applied as real objects, at a pace,
with accidents of its own on top.

The scenario is generated from its YAML at start (deterministic). Its people, GitOps and autoscaler
create, change and delete namespaces, workloads, configs, services, policies and autoscalers. Images
named in the scenario do not exist, so every container runs a tiny real image instead; the scenario's
image and version stay on the pod template, so a new version is a real rollout. Replicas and requests
are kept small enough for a test node. Nodes are the cloud's business and are not created.
Progress is kept in a ConfigMap, so a restarted player goes on where it stopped.
"""
from copy import deepcopy
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import random
import tempfile
import threading
import time

IMAGE = 'registry.k8s.io/pause:3.10'
JOB_IMAGE = 'registry.k8s.io/busybox:1.27.2'
REPLICAS = 2
SMALL = {'requests': {'cpu': '1m', 'memory': '8Mi'}, 'limits': {'cpu': '20m', 'memory': '32Mi'}}
NOTE = 'scenario.mnemosyne.art/image'


def realize(obj):
    """The scenario's object as something a small real cluster can run."""
    obj = deepcopy(obj)
    kind = obj['kind']
    spec = obj.get('spec') or {}
    if kind in ('Deployment', 'StatefulSet'):
        spec['replicas'] = min(int(spec.get('replicas', 1)), REPLICAS)
        spec.pop('volumeClaimTemplates', None)
    if kind == 'HorizontalPodAutoscaler':
        spec['maxReplicas'] = min(int(spec.get('maxReplicas', REPLICAS)), REPLICAS)
        spec['minReplicas'] = min(int(spec.get('minReplicas', 1)), spec['maxReplicas'])
    template = (spec.get('template') if kind in ('Deployment', 'StatefulSet', 'DaemonSet')
                else spec.get('jobTemplate', {}).get('spec', {}).get('template') if kind == 'CronJob' else None)
    if template:
        pod = template.setdefault('spec', {})
        images = []
        for c in pod.get('containers', []) + pod.get('initContainers', []):
            images.append(c.get('image', ''))
            c['image'] = JOB_IMAGE if kind == 'CronJob' else IMAGE
            if kind == 'CronJob':
                c['command'], c['args'] = ['true'], []
            else:
                c.pop('command', None)
                c.pop('args', None)
            for probe in ('livenessProbe', 'readinessProbe', 'startupProbe'):
                c.pop(probe, None)
            c['resources'] = deepcopy(SMALL)
            c.pop('volumeMounts', None)
        pod.pop('volumes', None)
        template.setdefault('metadata', {}).setdefault('annotations', {})[NOTE] = ','.join(images)
    return obj


def at(op):
    return datetime.fromisoformat(op['at'])


class Player:
    def __init__(self, scenario: Path, pace: float, api, namespace: str, *, seed=0, accidents=True):
        from kubernetes import client, dynamic
        self.api, self.namespace, self.pace, self.rng = api, namespace, pace, random.Random(seed)
        self.dynamic = dynamic.DynamicClient(api)
        self.core = client.CoreV1Api(api)
        self.apps = client.AppsV1Api(api)
        self.accidents = accidents
        self.stop = threading.Event()
        from mnemosyne.scenario.generate import main as generate
        self.out = Path(tempfile.mkdtemp())
        import sys
        argv, sys.argv = sys.argv, ['generate', str(scenario), '--out', str(self.out)]
        try:
            generate()
        finally:
            sys.argv = argv
        name = next(self.out.iterdir()).name
        self.ops = [json.loads(line) for line in open(self.out/name/'ops.jsonl')]
        self.namespaces = sorted({o['object']['metadata'].get('namespace') for o in self.ops} - {None})

    # -- progress ----------------------------------------------------------------------------
    def progress(self):
        try:
            cm = self.core.read_namespaced_config_map('scenario-progress', self.namespace)
            return json.loads(cm.data['progress'])
        except Exception:
            return {'index': 0, 'started': datetime.now(timezone.utc).isoformat()}

    def save(self, state):
        body = {'metadata': {'name': 'scenario-progress'}, 'data': {'progress': json.dumps(state)}}
        try:
            self.core.replace_namespaced_config_map('scenario-progress', self.namespace, body)
        except Exception:
            self.core.create_namespaced_config_map(self.namespace, body)

    # -- operations ----------------------------------------------------------------------------
    def apply(self, op):
        obj = op['object']
        if obj['kind'] == 'Node':
            return
        resource = self.dynamic.resources.get(api_version=obj['apiVersion'], kind=obj['kind'])
        ns = obj['metadata'].get('namespace')
        if op['op'] == 'delete':
            try:
                resource.delete(name=obj['metadata']['name'], namespace=ns)
            except Exception:
                pass
            return
        body = realize(obj)
        body['metadata'].setdefault('annotations', {})['scenario.mnemosyne.art/actor'] = \
            f"{op.get('actor_kind', '')}:{op.get('actor', '')}"
        resource.server_side_apply(body=body, name=obj['metadata']['name'], namespace=ns,
                                   field_manager='scenario', force_conflicts=True)

    def accident(self):
        """Things that happen on their own: a pod dies, a rollout fails and is rolled back, a spike."""
        kind = self.rng.choice(['pod', 'pod', 'rollout', 'spike'])
        ns = self.rng.choice(self.namespaces)
        if kind == 'pod':
            pods = self.core.list_namespaced_pod(ns).items
            if pods:
                victim = self.rng.choice(pods).metadata.name
                self.core.delete_namespaced_pod(victim, ns)
                return f'pod {ns}/{victim} died'
        deployments = self.apps.list_namespaced_deployment(ns).items
        if not deployments:
            return None
        d = self.rng.choice(deployments)
        name = d.metadata.name
        if kind == 'rollout':
            broken = {'spec': {'template': {'spec': {'containers': [
                {'name': d.spec.template.spec.containers[0].name, 'image': IMAGE.replace('3.10', 'no-such-version')}]}}}}
            self.apps.patch_namespaced_deployment(name, ns, broken)
            self.stop.wait(self.rng.uniform(300, 1200))
            self.apps.patch_namespaced_deployment(name, ns, {'spec': {'template': {'spec': {'containers': [
                {'name': d.spec.template.spec.containers[0].name, 'image': IMAGE}]}}}})
            return f'rollout of {ns}/{name} failed and was rolled back'
        self.apps.patch_namespaced_deployment_scale(name, ns, {'spec': {'replicas': REPLICAS * 2}})
        self.stop.wait(self.rng.uniform(600, 1800))
        self.apps.patch_namespaced_deployment_scale(name, ns, {'spec': {'replicas': d.spec.replicas or 1}})
        return f'spike on {ns}/{name}'

    def accidents_loop(self):
        while not self.stop.is_set():
            self.stop.wait(self.rng.expovariate(1 / (3 * 3600)))
            try:
                what = self.accident()
                if what:
                    print('accident:', what, flush=True)
            except Exception as exc:
                print('accident failed:', type(exc).__name__, exc, flush=True)

    def run(self):
        state = self.progress()
        started = datetime.fromisoformat(state['started'])
        origin = at(self.ops[0])
        if self.accidents:
            threading.Thread(target=self.accidents_loop, daemon=True).start()
        for i in range(state['index'], len(self.ops)):
            op = self.ops[i]
            due = started.timestamp() + (at(op) - origin).total_seconds() / self.pace
            wait = due - time.time()
            if wait > 0 and self.stop.wait(wait):
                return
            try:
                self.apply(op)
            except Exception as exc:
                print('op failed:', i, op['op'], op['object']['kind'], type(exc).__name__, str(exc)[:200], flush=True)
            if i % 50 == 0:
                self.save({'index': i + 1, 'started': state['started']})
        self.save({'index': len(self.ops), 'started': state['started'], 'done': True})
        print('the scenario year is lived', flush=True)
        self.stop.wait()


def main():
    import argparse
    from kubernetes import config, client
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('scenario', type=Path)
    ap.add_argument('--pace', type=float, default=24., help='scenario seconds per real second')
    ap.add_argument('--namespace', default=os.environ.get('POD_NAMESPACE', 'scenario'))
    ap.add_argument('--no-accidents', action='store_true')
    a = ap.parse_args()
    config.load_incluster_config()
    Player(a.scenario, a.pace, client.ApiClient(), a.namespace, accidents=not a.no_accidents).run()


if __name__ == '__main__':
    main()
