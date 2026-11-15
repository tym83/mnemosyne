import json
from pathlib import Path
import unittest

from mnemosyne.scenario.live import realize, IMAGE, NOTE, REPLICAS


@unittest.skipUnless(Path("out/scenarios/leonia/ops.jsonl").exists(), "generate the Leonia scenario first")
class RealizeTests(unittest.TestCase):
    def ops(self):
        for line in open(Path('out/scenarios/leonia/ops.jsonl')):
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
