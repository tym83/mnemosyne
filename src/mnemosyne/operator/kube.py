"""Explicit resource inventory; no wildcard permission that accidentally grants Secrets."""
from mnemosyne.state.collect import secret_resource


def connect():
    import os
    from kubernetes import client, config
    if os.getenv('KUBERNETES_SERVICE_HOST'):
        config.load_incluster_config()
    else:
        config.load_kube_config()
    return client.ApiClient()


def snapshot(api, resources, namespace=None, include_secrets=False):
    from kubernetes.dynamic import DynamicClient
    dynamic = DynamicClient(api)
    objects = []
    for entry in resources:
        resource = dynamic.resources.get(api_version=entry['apiVersion'], kind=entry['kind'])
        if resource.name != entry['resource']:
            raise ValueError('inventory resource and discovered kind disagree')
        if (secret_resource(entry['kind']) or secret_resource(resource.name)) and not include_secrets:
            raise ValueError('Secret inventory requires explicit owner opt-in')
        if namespace and not resource.namespaced:
            if entry['apiVersion'] == 'v1' and entry['kind'] == 'Namespace':
                objects.append(resource.get(name=namespace).to_dict())
            continue
        if entry.get('names'):
            if resource.namespaced and not namespace:
                raise ValueError('named inventory requires snapshotNamespace')
            for name in entry['names']:
                kwargs = {'name': name}
                if resource.namespaced:
                    kwargs['namespace'] = namespace
                objects.append(resource.get(**kwargs).to_dict())
            continue
        token = None
        seen = set()
        while True:
            kwargs = {'limit': 500, '_continue': token}
            if resource.namespaced and namespace:
                kwargs['namespace'] = namespace
            page = resource.get(**kwargs).to_dict()
            objects.extend(page['items'])
            token = page.get('metadata', {}).get('continue')
            if not token:
                break
            if token in seen:
                raise ValueError('repeated API pagination token')
            seen.add(token)
    # A scoped backup also needs the namespace in a fresh API server.
    if namespace and not any(o['apiVersion'] == 'v1' and o['kind'] == 'Namespace' for o in objects):
        objects.append({'apiVersion': 'v1', 'kind': 'Namespace', 'metadata': {'name': namespace}})
    return objects


def publish(api, namespace, records):
    from kubernetes import client
    from mnemosyne.atelier import GROUP, VERSION, KINDS
    from kubernetes.client.exceptions import ApiException
    custom = client.CustomObjectsApi(api)
    for source in sorted(records, key=lambda o: o['kind'] == 'Atelier'):
        body = dict(source)
        body['metadata'] = {**source['metadata'], 'namespace': namespace}
        status = body.pop('status', None)
        plural = KINDS[body['kind']]
        args = GROUP, VERSION, namespace, plural
        name = body['metadata']['name']
        try:
            custom.create_namespaced_custom_object(*args, body)
        except ApiException as exc:
            if exc.status != 409:
                raise
            custom.patch_namespaced_custom_object(*args, name, {'spec': body['spec']})
        if status:
            custom.patch_namespaced_custom_object_status(*args, name, {'status': status})


def restored_lineage(api, namespace, name):
    """A fresh PVC can resume the artist state recovered into ordinary CRs."""
    from kubernetes import client
    from mnemosyne.atelier import GROUP, VERSION
    from mnemosyne.lineage import Lineage
    custom = client.CustomObjectsApi(api)
    root = custom.get_namespaced_custom_object(GROUP, VERSION, namespace, 'ateliers', name)
    if 'lineage' not in root['spec']:
        return None
    records = [root]
    for artist in root['spec']['artists']:
        for plural in ('artists', 'biographies'):
            records.append(custom.get_namespaced_custom_object(GROUP, VERSION, namespace, plural, artist))
    return Lineage.from_objects(records, root['spec']['lineage']['cluster']).state()
