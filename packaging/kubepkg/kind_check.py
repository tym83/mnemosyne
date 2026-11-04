"""Install the signed package through the real operator into a NEW kind cluster.

Never uses the current context; keeps the cluster and evidence even on failure.
No image builds, artist invocations, Secret queries or automatic cleanup.
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import uuid


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--index', required=True, help='Published signed index, reachable from kind')
    p.add_argument('--public-key', required=True, type=Path)
    p.add_argument('--operator-version', required=True, help='Reviewed kubepkg Helm release version')
    p.add_argument('--kubepkg', default='kubepkg')
    p.add_argument('--provider', choices=['docker', 'podman', 'nerdctl'], default='podman')
    p.add_argument('--output', required=True, type=Path)
    p.add_argument('--active', action='store_true', help='Also require the atelier controller; recipient and pull credentials must be provisioned separately')
    args = p.parse_args()
    if not shutil.which(args.provider):
        p.error(f'{args.provider} is not installed; no cluster was touched')
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    name = 'mnemosyne-pkg-' + uuid.uuid4().hex[:8]
    context = 'kind-' + name
    env = dict(os.environ, KUBECONFIG=str(out / 'kubeconfig'), KIND_EXPERIMENTAL_PROVIDER=args.provider)
    def run(command, filename=None, timeout=900):
        with (out / 'commands.log').open('a') as log:
            log.write(json.dumps(command) + '\n')
        if filename:
            with (out / filename).open('w') as log:
                subprocess.run(command, check=True, env=env, stdout=log, stderr=subprocess.STDOUT, timeout=timeout)
        else:
            subprocess.run(command, check=True, env=env, timeout=timeout)
    kubectl = ['kubectl', '--kubeconfig', env['KUBECONFIG'], '--context', context]
    kp = [args.kubepkg, '--context', context]
    (out / 'cluster.json').write_text(json.dumps({'name': name, 'context': context, 'active': args.active}, indent=2))
    run(['kind', 'create', 'cluster', '--name', name, '--kubeconfig', env['KUBECONFIG'], '--wait', '120s'], 'kind.log')
    run(['helm', '--kubeconfig', env['KUBECONFIG'], '--kube-context', context, 'install', 'kubepkg',
         'oci://ghcr.io/kuberoot-dev/charts/kubepkg', '--version', args.operator_version,
         '--namespace', 'kubepkg-system', '--create-namespace', '--wait', '--timeout', '5m'], 'operator.log')
    run(kp + ['repo', 'add', 'mnemosyne-test', args.index, '--public-key', str(args.public_key.resolve())])
    run(kubectl + ['wait', 'repository.kubepkg.dev/mnemosyne-test', '--for=condition=Ready', '--timeout=180s'])
    run(kp + ['install', 'mnemosyne@0.2.0', '--yes'], 'install.log')
    run(kubectl + ['wait', 'package.kubepkg.dev/mnemosyne', '--for=condition=Ready', '--timeout=600s'])
    if args.active:
        run(kubectl + ['-n', 'mnemosyne', 'rollout', 'status', 'deployment/mnemosyne-atelier-controller', '--timeout=180s'])
    run(kubectl + ['get', 'package.kubepkg.dev/mnemosyne', '-o', 'yaml'], 'package.yaml')
    run(kubectl + ['get', 'crd', '-o', 'name'], 'crds.txt')
    run(kp + ['sbom', '--cluster', '-o', str(out / 'sbom.cdx.json')])
    print(f'PASS ({"active controller" if args.active else "inactive catalog"}); cluster retained: {name}; evidence: {out}')

if __name__ == '__main__':
    main()
