"""Read-only, namespace-scoped Kubernetes sensor. Never requests Secrets.

Only standard APIs; unknown/forbidden observations remain None, not zero.
Inventory is private sensor state and must never be given to an artist.
"""
from datetime import datetime, timezone
from pathlib import Path
import json
import subprocess

RESOURCES = ('pods', 'deployments.apps', 'statefulsets.apps', 'daemonsets.apps',
             'jobs.batch', 'cronjobs.batch', 'services', 'endpoints',
             'networkpolicies.networking.k8s.io', 'roles.rbac.authorization.k8s.io',
             'rolebindings.rbac.authorization.k8s.io', 'resourcequotas', 'events')


def quantity(value):
    s = str(value)
    for suffix, factor in [('Ki', 1024), ('Mi', 1024**2), ('Gi', 1024**3),
                           ('Ti', 1024**4), ('n', 1e-9), ('u', 1e-6), ('m', .001),
                           ('K', 1000), ('M', 1e6), ('G', 1e9)]:
        if s.endswith(suffix):
            return float(s[:-len(suffix)])*factor
    return float(s)


API = {'pods': 'api/v1', 'services': 'api/v1', 'endpoints': 'api/v1', 'resourcequotas': 'api/v1',
       'events': 'api/v1', 'deployments.apps': 'apis/apps/v1', 'statefulsets.apps': 'apis/apps/v1',
       'daemonsets.apps': 'apis/apps/v1', 'jobs.batch': 'apis/batch/v1', 'cronjobs.batch': 'apis/batch/v1',
       'networkpolicies.networking.k8s.io': 'apis/networking.k8s.io/v1',
       'roles.rbac.authorization.k8s.io': 'apis/rbac.authorization.k8s.io/v1',
       'rolebindings.rbac.authorization.k8s.io': 'apis/rbac.authorization.k8s.io/v1'}


class NotFound(Exception):
    pass


def incluster(api):
    """GET through the controller's own service account; forbidden stays unknown."""
    from kubernetes.client.exceptions import ApiException
    def fetch(path):
        try:
            return api.call_api(path, 'GET', response_type='object', auth_settings=['BearerToken'],
                                _return_http_data_only=True)
        except ApiException as exc:
            if exc.status == 404:
                raise NotFound(path) from exc
            raise
    return fetch


class Sensor:
    def __init__(self, namespace='tenant-scheherazade', runner=subprocess.run, fetch=None):
        # Without an in-cluster fetch this is the workshop development sensor.
        if fetch is None and namespace != 'tenant-scheherazade':
            raise ValueError('workshop sensor is restricted to tenant-scheherazade')
        self.namespace, self.runner, self.fetch = namespace, runner, fetch
        self.base = ['kubectl', '--kubeconfig', str(Path('~/workshop.txt').expanduser()),
                     '--context', 'admin@workshop', '--request-timeout=15s', '-n', namespace]

    def read(self, previous=None, now=None):
        missing = []
        def get(resource, raw=False):
            if self.fetch is not None:
                # Without a namespace the sensor feels the whole cluster (read-only).
                scope = f'/namespaces/{self.namespace}' if self.namespace else ''
                path = resource if raw else f'/{API[resource]}{scope}/{resource.split(".")[0]}'
                try:
                    return self.fetch(path)
                except NotFound:
                    if resource == '/api/v1/namespaces/'+self.namespace:
                        return {'absent': True}
                    missing.append(resource)
                    return None
                except Exception:
                    missing.append(resource)
                    return None
            args = ['get', '--raw', resource] if raw else ['get', resource, '-o', 'json']
            try:
                result = self.runner(self.base + args, capture_output=True, text=True, timeout=20)
                if result.returncode:
                    if resource == '/api/v1/namespaces/'+self.namespace and '(NotFound)' in result.stderr:
                        return {'absent': True}
                    missing.append(resource)
                    return None
                return json.loads(result.stdout)
            except (subprocess.TimeoutExpired, json.JSONDecodeError):
                missing.append(resource)
                return None
        objects = {k: get(k) for k in RESOURCES}
        if self.namespace:
            ns = get('/api/v1/namespaces/'+self.namespace, True)
            metrics = get('/apis/metrics.k8s.io/v1beta1/namespaces/'+self.namespace+'/pods', True)
        else:
            ns = {'metadata': {'uid': 'cluster'}}
            metrics = get('/apis/metrics.k8s.io/v1beta1/pods', True)
        def items(k):
            return (objects[k] or {}).get('items', [])
        pods = items('pods')
        inventory = {p['metadata']['uid']: [c.get('image', '') for c in p['spec'].get('containers', [])] for p in pods}
        versions = sorted({v for vs in inventory.values() for v in vs})
        old = (previous or {}).get('inventory', {})
        events = []
        if previous and objects['pods'] is not None and previous.get('pods_observed'):
            if inventory.keys() != old.keys(): events.append('deploy')
            if versions != previous.get('versions', []): events.append('upgrade')
        exists = ns is not None and not ns.get('absent')
        # A failed GET is unknown, never evidence of tenant deletion.
        if previous and ns is not None and ns.get('absent') and previous.get('namespace_uid'):
            events.append('tenant_deletion')
        if previous and exists and previous.get('namespace_absent'):
            events.append('tenant_birth')
        if previous and exists and previous.get('namespace_uid') and ns['metadata']['uid'] != previous['namespace_uid']:
            events.extend(['tenant_deletion', 'tenant_birth'])
        event_ids = {e['metadata']['uid']+':'+str(e.get('count', 1)) for e in items('events')}
        old_events = set((previous or {}).get('event_ids', []))
        failures = sum(e.get('type') == 'Warning' and e['metadata']['uid']+':'+str(e.get('count', 1)) not in old_events for e in items('events'))
        if failures: events.append('failure')
        if previous and not events and not missing: events.append('quiet')
        requests = {k: sum(quantity(c.get('resources', {}).get('requests', {}).get(k, 0))
                          for p in pods for c in p['spec'].get('containers', [])) for k in ('cpu', 'memory')}
        usage = {k: sum(quantity(c.get('usage', {}).get(k, 0)) for p in (metrics or {}).get('items', [])
                       for c in p.get('containers', [])) for k in requests}
        utilisation = {k: usage[k]/requests[k] if metrics is not None and requests[k] else None for k in requests}
        roles = items('roles.rbac.authorization.k8s.io')
        broad = any('*' in rule.get('verbs', []) or '*' in rule.get('resources', []) for role in roles for rule in role.get('rules', []))
        policies = items('networkpolicies.networking.k8s.io')
        denied = any(not p['spec'].get('podSelector') and not p['spec'].get('ingress') and
                     'Ingress' in p['spec'].get('policyTypes', ['Ingress']) for p in policies)
        controllers = items('deployments.apps') + items('statefulsets.apps')
        stamp = now or datetime.now(timezone.utc).isoformat()
        created = (ns or {}).get('metadata', {}).get('creationTimestamp')
        age = max(0, (datetime.fromisoformat(stamp.replace('Z', '+00:00'))-datetime.fromisoformat(created.replace('Z', '+00:00'))).days) if created else None
        return dict(at=stamp, scope=self.namespace, missing=missing, inventory=inventory,
            pods_observed=objects['pods'] is not None, namespace_uid=(ns or {}).get('metadata', {}).get('uid'), namespace_absent=bool((ns or {}).get('absent')), 
            event_ids=sorted(event_ids), versions=versions, events=events,
            configuration=dict(workload_kinds={k: len(items(k)) if objects[k] is not None else None for k in RESOURCES[:6]},
                tenants=1 if exists else 0 if (ns or {}).get('absent') else None, network_closed=float(denied) if objects['networkpolicies.networking.k8s.io'] else None,
                rbac_local_strict=float(not broad) if roles else None, rbac_effective_strict=None,
                ha=sum(c['spec'].get('replicas', 1)>1 for c in controllers)/len(controllers) if controllers else None,
                service_links=sum(len(sub.get('addresses', [])) for s in items('endpoints') for sub in s.get('subsets', [])) if objects['endpoints'] is not None else None,
                placement_spread=len({p['spec'].get('nodeName') for p in pods if p['spec'].get('nodeName')}),
                age_days=age, cluster_version=None),
            load=dict(utilisation=utilisation, churn=len(set(inventory)^set(old))/max(1,len(inventory)) if previous and objects['pods'] is not None else None,
                scheduling_pressure=sum(p.get('status', {}).get('phase')=='Pending' for p in pods)/len(pods) if pods else None,
                unready=sum(not any(c.get('type')=='Ready' and c.get('status')=='True' for c in p.get('status', {}).get('conditions', [])) for p in pods)/len(pods) if pods else None,
                latency_ms=None), failures=failures)
