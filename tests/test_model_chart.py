"""Check the actual rendered manifest, including the optional model lifecycle."""
import shutil
import subprocess
import tempfile
from pathlib import Path
import unittest
import yaml


@unittest.skipUnless(shutil.which('helm'), 'helm unavailable')
class ChartTests(unittest.TestCase):
    def render(self, values):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'values.yaml'
            path.write_text(yaml.safe_dump(values))
            result = subprocess.run(['helm', 'template', 'test', 'charts/mnemosyne', '-f', str(path)],
                                    capture_output=True, text=True, check=True)
            return list(yaml.safe_load_all(result.stdout))

    def test_chamber_creates_no_model_pod_or_volume(self):
        docs = self.render({})
        self.assertEqual([d['kind'] for d in docs], ['ConfigMap'])

    def test_window_lifecycle_pvc_retention_and_secret_references(self):
        docs = self.render(dict(work=dict(enabled=True, image='runner:test', command=['python', 'night.py'],
            priorityClassName='existing-lowest', artifacts={'existingClaim': 'art'},
            credentials=[dict(env='MODEL_KEY', secretKeyRef=dict(name='api-key', key='token'))]),
            servers=[dict(name='text', image='llama:test', command=['llama-server'], args=['-m','/models/m.gguf'],
                          port=8080, healthPath='/health', resources={'limits': {'memory': '26Gi'}},
                          weights=dict(existingClaim='', size='40Gi'))], notagen=dict(enabled=True)))
        cron = next(d for d in docs if d['kind'] == 'CronJob')
        spec = cron['spec']['jobTemplate']['spec']
        pod = spec['template']['spec']
        self.assertEqual(cron['spec']['concurrencyPolicy'], 'Forbid')
        self.assertEqual(spec['backoffLimit'], 0)
        self.assertGreater(spec['activeDeadlineSeconds'], 0)
        self.assertEqual(pod['initContainers'][0]['restartPolicy'], 'Always')
        self.assertIn('startupProbe', pod['initContainers'][0])
        self.assertFalse(pod['automountServiceAccountToken'])
        self.assertNotIn('env', pod['initContainers'][0])
        env = pod['containers'][0]['env']
        self.assertEqual(next(e for e in env if e['name']=='MODEL_KEY')['valueFrom']['secretKeyRef']['name'], 'api-key')
        self.assertEqual(next(e for e in env if e['name']=='MNEMOSYNE_NOTAGEN')['value'], 'self-hosted')
        self.assertEqual(len([d for d in docs if d['kind']=='PersistentVolumeClaim']), 2)
        self.assertTrue(all(d['metadata']['annotations']['helm.sh/resource-policy']=='keep'
                            for d in docs if d['kind']=='PersistentVolumeClaim'))
        self.assertNotIn('Secret', [d['kind'] for d in docs])
