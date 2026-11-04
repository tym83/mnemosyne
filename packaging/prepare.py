"""Stage portable packages without changing any platform checkout.

All output goes into a NEW directory. --release requires Actions digest values
and a complete owner values file; without it only the inactive catalog is built.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import yaml

ROOT = Path(__file__).resolve().parents[1]

def merge(left, right):
    for key, value in right.items():
        if isinstance(value, dict) and isinstance(left.get(key), dict):
            merge(left[key], value)
        else:
            left[key] = value
    return left


def prepare(args):
    core_values = yaml.safe_load((ROOT / 'charts/mnemosyne/values.yaml').read_text())
    for file in args.values:
        merge(core_values, yaml.safe_load(file.read_text()))
    addon = core_values['addon']
    if args.release:
        for role in ('controller', 'studio'):
            image = addon['images'][role]
            if not re.fullmatch(r'sha256:[0-9a-f]{64}', image['digest']):
                raise ValueError(f'{role}: real Actions digest required')
        if not addon['enabled']:
            raise ValueError('release requires addon.enabled: true and complete owner values')
    elif addon['enabled']:
        raise ValueError('active packages require --release')
    args.output.mkdir(parents=True, exist_ok=False)
    out = args.output
    co = out / 'cozystack'
    shutil.copytree(ROOT / 'packaging/cozystack', co)
    shutil.copytree(ROOT / 'charts/mnemosyne', co / 'system/mnemosyne-core')
    shutil.copytree(ROOT / 'charts/mnemosyne/crds', co / 'system/mnemosyne-rd/crds')
    cozy = args.cozystack / 'packages/library/cozy-lib'
    shutil.copytree(cozy, co / 'library/cozy-lib')
    shutil.copytree(cozy, co / 'apps/mnemosyne/charts/cozy-lib')
    if args.release:
        app_values_path = co / 'apps/mnemosyne/values.yaml'
        app_values = yaml.safe_load(app_values_path.read_text())
        app_values['images'] = addon['images']
        app_values_path.write_text(yaml.safe_dump(app_values, sort_keys=False))
    kp = out / 'kubepkg'
    kp.mkdir()
    shutil.copytree(ROOT / 'charts/mnemosyne', kp / 'charts/mnemosyne')
    recipe = yaml.safe_load((ROOT / 'packaging/kubepkg/recipe.yaml').read_text())
    if args.release:
        recipe['spec']['charts']['mnemosyne']['values'] = core_values
        recipe['spec']['package']['images'] = [f"{v['repository']}@{v['digest']}" for v in addon['images'].values()]
        ready = recipe['spec']['package']['variants'][0]['components'][0]['install']['readyWhen']
        ready.append({'apiVersion': 'apps/v1', 'kind': 'Deployment', 'name': 'mnemosyne-atelier-controller', 'condition': 'Available'})
        # Site-specific key/commission values belong in a private package or in
        # Package values. Never put key bytes or tokens in an owner values file.
    (kp / 'recipe.yaml').write_text(yaml.safe_dump(recipe, sort_keys=False))
    subprocess.run(['helm', 'lint', str(kp / 'charts/mnemosyne')], check=True)
    if args.release:
        values = out / 'release-values.yaml'
        values.write_text(yaml.safe_dump(core_values, sort_keys=False))
        subprocess.run(['helm', 'template', 'mnemosyne', str(kp / 'charts/mnemosyne'), '-n', 'mnemosyne', '-f', str(values)], check=True, stdout=subprocess.DEVNULL)
    manifest = {}
    for path in sorted(out.rglob('*')):
        if path.is_file():
            manifest[str(path.relative_to(out))] = hashlib.sha256(path.read_bytes()).hexdigest()
    (out / 'sources.sha256.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print(f'Staged {"release" if args.release else "inactive catalog only"}: {out}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--cozystack', type=Path, default=Path.home() / 'projects/cozystack')
    parser.add_argument('--release', action='store_true')
    parser.add_argument('--values', type=Path, action='append', default=[])
    prepare(parser.parse_args())
