"""Disposable kind e2e using Podman/nerdctl, source bootstrap, no image builds.

Run inside an equipped studio or CI. Artifacts and key remain outside kind.
Only the newly created mnemo-e2e-* cluster is deleted; no pre-existing cluster
is accepted. No automatic cleanup on failure: retain evidence for inspection.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import uuid
import yaml


def run(*args, **kwargs):
    return subprocess.run(list(map(str,args)),check=True,**kwargs)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--provider',choices=['podman','nerdctl'],default='podman')
    p.add_argument('--base-image',required=True,help='Python 3.12 image@sha256:digest for source bootstrap')
    args=p.parse_args()
    for binary in ('kind','kubectl','helm',args.provider):
        if not shutil.which(binary): raise SystemExit(f'missing {binary}; Docker fallback is forbidden')
    if '@sha256:' not in args.base_image: p.error('base image must be pinned by digest')
    root=args.output.resolve();root.mkdir(parents=True,exist_ok=False)
    name='mnemo-e2e-'+uuid.uuid4().hex[:10]
    env={**os.environ,'KIND_EXPERIMENTAL_PROVIDER':args.provider,'MNEMO_E2E_BASE_IMAGE':args.base_image}
    repo=Path(__file__).resolve().parents[2]
    works=root/'works';works.mkdir()
    cfg=root/'kind.yaml';kc=root/'kubeconfig'
    cfg.write_text(yaml.safe_dump({'kind':'Cluster','apiVersion':'kind.x-k8s.io/v1alpha4',
        'nodes':[{'role':'control-plane','extraMounts':[
            {'hostPath':str(repo),'containerPath':'/mnemo-e2e/source','readOnly':True},
            {'hostPath':str(works),'containerPath':'/mnemo-e2e/works'}]}]}))
    def create(): run('kind','create','cluster','--name',name,'--config',cfg,'--kubeconfig',kc,env=env)
    def kube(*command,**kw): return run('kubectl','--kubeconfig',kc,'--context','kind-'+name,*command,**kw)
    create()
    fixture=[{'apiVersion':'v1','kind':'Namespace','metadata':{'name':'mnemo-fixture'}},
             {'apiVersion':'v1','kind':'ConfigMap','metadata':{'name':'memory','namespace':'mnemo-fixture'},
              'data':{'remember':'the same bytes after a new API server'}}]
    kube('apply','-f','-',input=yaml.safe_dump_all(fixture),text=True)
    # Snapshot the normalized live version, including API defaults, not source YAML.
    live=json.loads(kube('get','configmap','memory','-n','mnemo-fixture','-o','json',capture_output=True,text=True).stdout)
    from mnemosyne.state.collect import normalize
    expected=normalize(live)
    expected_namespace=normalize(json.loads(kube('get','namespace','mnemo-fixture','-o','json',capture_output=True,text=True).stdout))
    (root/'expected.json').write_text(json.dumps(expected))
    kube('create','namespace','mnemosyne')
    from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey
    from mnemosyne.weave.backup import write_new
    write_new(root/'recipient.key', X25519PrivateKey.generate().private_bytes_raw())
    kube('-n','mnemosyne','create','secret','generic','recipient','--from-file=recipient.key='+str(root/'recipient.key'))
    plan=json.loads((repo/'src/mnemosyne/music/schools/plans/tempo_canon.json').read_text())
    # Existing method study explicitly used as a technical fixture, no quality claim.
    digest=args.base_image.split('@')[1]
    values={'addon':{'enabled':True,'render':False,'images':{r:{'digest':digest} for r in ('controller','studio')},
        'key':{'secretName':'recipient'},'window':{'kind':'always'},'snapshotNamespace':'mnemo-fixture',
        'inventory':[{'apiVersion':'v1','kind':'Namespace','resource':'namespaces'},
                     {'apiVersion':'v1','kind':'ConfigMap','resource':'configmaps','names':['memory']}],
        'commissions':[{'idea':'Existing method study: technical recovery fixture',
                        'method':'tempo_canon study from the repository','plan':{**plan,'seed':plan['seed']+i}} for i in range(3)],
        'resources':{'requests':{'cpu':'100m','memory':'512Mi'},'limits':{'cpu':'2','memory':'2Gi'}}}}
    vp=root/'values.yaml';vp.write_text(yaml.safe_dump(values))
    run('helm','install','e2e',repo/'charts/mnemosyne','--namespace','mnemosyne','--kubeconfig',kc,
        '--kube-context','kind-'+name,'-f',vp,'--post-renderer',repo/'hack/addon/source_postrender.py',env=env)
    deadline=time.monotonic()+1800
    complete=[]
    while time.monotonic()<deadline:
        complete=list(works.glob('*/*/complete.json'))
        if complete: break
        time.sleep(5)
    if not complete: raise RuntimeError('night timed out; cluster and source logs retained')
    report=json.loads(complete[0].read_text())
    if report.get('phase')!='Verified' or not report.get('loss_tolerance_verified'): raise RuntimeError(report)
    kube('-n','mnemosyne','wait','--for=condition=complete','job','-l','mnemosyne.art/atelier=e2e-atelier','--timeout=120s')
    from mnemosyne.cli import main as cli
    cli(['works','export','--source',str(works),'--output',str(root/'export')])
    relative=complete[0].parent.relative_to(works)
    full=root/'export'/relative/'woven'
    scores=root/'survivors'; scores.mkdir()
    for path in sorted(full.glob('*.musicxml'))[:2]: shutil.copyfile(path,scores/path.name)
    run('kind','delete','cluster','--name',name,env=env)
    create()
    cli(['restore','--works',str(scores),'--key',str(root/'recipient.key'),'--apply',
         '--kubeconfig',str(kc),'--context','kind-'+name,'--output',str(root/'restore')])
    actual=normalize(json.loads(kube('get','configmap','memory','-n','mnemo-fixture','-o','json',capture_output=True,text=True).stdout))
    if actual!=expected: raise RuntimeError('restored ConfigMap differs')
    actual_namespace=normalize(json.loads(kube('get','namespace','mnemo-fixture','-o','json',capture_output=True,text=True).stdout))
    if actual_namespace!=expected_namespace: raise RuntimeError('restored Namespace differs')
    (root/'result.json').write_text(json.dumps({'identical':True,'frame_decode_verified':True,
        'lost_works':1,'total_works':3,'all_subsets_verified':True,'new_cluster':name,'scope':'Namespace + live ConfigMap; not volume data or whole-cluster conformance'},indent=2))
    print((root/'result.json').read_text())


if __name__=='__main__': main()
