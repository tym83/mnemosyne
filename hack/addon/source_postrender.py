#!/usr/bin/env python3
"""kind-only source bootstrap; never build images, touch workshop or use Docker."""
import json
import os
import sys
import yaml

image = os.environ['MNEMO_E2E_BASE_IMAGE']
if '@sha256:' not in image:
    raise ValueError('pin the bootstrap Python 3.12 image by digest')

def bootstrap(pod, command):
    pod['securityContext'] = {'runAsUser': 0}
    pod['volumes'] = [v for v in pod.get('volumes', []) if v['name'] != 'works']
    pod['volumes'] += [{'name':'source','hostPath':{'path':'/mnemo-e2e/source'}},
                       {'name':'works','hostPath':{'path':'/mnemo-e2e/works'}}]
    container = pod['containers'][0]
    container['image'] = image
    container['resources'] = {'requests':{'cpu':'100m','memory':'512Mi'},'limits':{'cpu':'2','memory':'2Gi'}}
    container['securityContext'] = {'allowPrivilegeEscalation':False}
    container['volumeMounts'] = [m for m in container.get('volumeMounts', []) if m['name'] != 'works']
    container['volumeMounts'] += [{'name':'source','mountPath':'/source','readOnly':True},
                                 {'name':'works','mountPath':'/works'}]
    container.setdefault('env', []).append({'name':'PYTHONPATH','value':'/source/src:/tmp/deps'})
    container['command'] = ['sh','-ec',
        'python -m pip install --target /tmp/deps "/source[operator]" >/tmp/install.log 2>&1; exec "$@"',
        'source-bootstrap', *command]
    return pod

for doc in yaml.safe_load_all(sys.stdin):
    if not doc: continue
    if doc['kind']=='ConfigMap' and 'runtime.json' in doc.get('data',{}):
        runtime = json.loads(doc['data']['runtime.json'])
        runtime['pod'] = bootstrap(runtime['pod'], ['python','-m','mnemosyne.operator.worker'])
        doc['data']['runtime.json'] = json.dumps(runtime)
    if doc['kind']=='Deployment' and doc['metadata']['name'].endswith('-controller'):
        pod = doc['spec']['template']['spec']
        command = ['python','-m','kopf', *pod['containers'][0]['command'][1:]]
        bootstrap(pod,command)
    print(yaml.safe_dump(doc,sort_keys=False)+'---')
