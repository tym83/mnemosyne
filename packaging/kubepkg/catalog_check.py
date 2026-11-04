"""Check signing and CycloneDX generation for a locally built catalog.

Serves only test chart archives and the signed index on loopback. The ephemeral
signing key is kept OUTSIDE the served directory. Does not publish or install.
"""
import argparse
import functools
import hashlib
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import subprocess
import threading
import yaml


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--recipe', type=Path, required=True)
    p.add_argument('--tree', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--kubepkg', default='kubepkg')
    args = p.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    site = out / 'site'
    charts = site / 'charts'
    charts.mkdir(parents=True)
    dist = out / 'dist'
    dist.mkdir()
    def run(command):
        subprocess.run([str(x) for x in command], check=True, timeout=120)
    recipe = yaml.safe_load(args.recipe.read_text())
    spec = recipe['spec']['package']
    spec.update(version=recipe['spec']['version'], build=recipe['spec']['build'])
    handler = functools.partial(SimpleHTTPRequestHandler, directory=str(site))
    server = ThreadingHTTPServer(('127.0.0.1', 0), handler)
    url = f'http://127.0.0.1:{server.server_port}'
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        for variant in spec['variants']:
            for component in variant['components']:
                chart = args.tree / component.pop('path')
                meta = yaml.safe_load((chart / 'Chart.yaml').read_text())
                run(['helm', 'package', chart, '-d', charts])
                archive = charts / f"{meta['name']}-{meta['version']}.tgz"
                component['chart'] = {'repository': url + '/charts', 'name': meta['name'], 'version': meta['version'],
                                      'digest': 'sha256:' + hashlib.sha256(archive.read_bytes()).hexdigest()}
        run(['helm', 'repo', 'index', charts, '--url', url + '/charts'])
        source = {'apiVersion': 'kubepkg.dev/v1', 'kind': 'PackageSource', 'metadata': recipe['metadata'], 'spec': spec}
        (dist / 'mnemosyne.yaml').write_text(yaml.safe_dump(source, sort_keys=False))
        run([args.kubepkg, 'repo', 'keygen', out / 'test-signing'])
        run([args.kubepkg, 'repo', 'index', dist, '-o', site / 'index.yaml', '--verify', '--sign-key', out / 'test-signing.key'])
        run([args.kubepkg, 'sbom', 'mnemosyne', '--repo', url + '/index.yaml', '--public-key', out / 'test-signing.pub',
             '--timestamp', '2026-11-04T00:00:00Z', '-o', out / 'catalog.cdx.json'])
        sbom = json.loads((out / 'catalog.cdx.json').read_text())
        assert sbom['bomFormat'] == 'CycloneDX' and sbom['specVersion'] == '1.6'
        print(f"PASS: signed local index, verified chart digest, CycloneDX {sbom['specVersion']}; {len(sbom.get('components', []))} components")
    finally:
        server.shutdown()
        server.server_close()

if __name__ == '__main__':
    main()
