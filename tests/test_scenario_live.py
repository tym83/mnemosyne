import json
from pathlib import Path
import tempfile
import unittest

from mnemosyne.scenario.live import realize, IMAGE, NOTE, REPLICAS

ROOT = Path(__file__).resolve().parents[1]
GENERATED = ROOT/'out/scenarios/leonia/ops.jsonl'


class RealizeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # The generated year is not in git: use the local one, or generate it (seeded, a few seconds).
        cls.path = GENERATED
        if not cls.path.exists():
            from mnemosyne.scenario.generate import run
            cls.tmp = tempfile.TemporaryDirectory()
            run(ROOT/'scenarios/leonia.yaml', Path(cls.tmp.name))
            cls.path = Path(cls.tmp.name)/'leonia/ops.jsonl'

    @classmethod
    def tearDownClass(cls):
        if hasattr(cls, 'tmp'):
            cls.tmp.cleanup()

    def ops(self):
        with open(self.path) as lines:
            for line in lines:
                yield json.loads(line)

    def test_workloads_run_a_real_tiny_image_and_keep_their_version(self):
        seen = set()
        for op in self.ops():
            obj = op['object']
            if obj['kind'] in ('Deployment', 'StatefulSet', 'CronJob') and obj['kind'] not in seen:
                seen.add(obj['kind'])
                out = realize(obj)
                spec = out['spec']
                template = spec['template'] if obj['kind'] != 'CronJob' else spec['jobTemplate']['spec']['template']
                containers = template['spec']['containers']
                self.assertTrue(all(c['image'] in (IMAGE, 'registry.k8s.io/busybox:1.27.2') for c in containers))
                self.assertTrue(template['metadata']['annotations'][NOTE])
                if obj['kind'] != 'CronJob':
                    self.assertLessEqual(spec['replicas'], REPLICAS)
                self.assertNotIn('volumeClaimTemplates', spec)
            if len(seen) == 3:
                break
        self.assertEqual(seen, {'Deployment', 'StatefulSet', 'CronJob'})


if __name__ == '__main__':
    unittest.main()
