import copy
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import yaml
from mnemosyne.atelier import crds, KINDS
from mnemosyne.cli import export_local
from mnemosyne.operator.policy import window, job_name


class PolicyTests(unittest.TestCase):
    def test_midnight_night_keeps_identity_and_deadline(self):
        policy = {'kind': 'night', 'startHour': 22, 'endHour': 6}
        self.assertEqual(window(policy, datetime(2026, 1, 2, 2, tzinfo=timezone.utc)), ('2026-01-01', 14400))
        self.assertIsNone(window(policy, datetime(2026, 1, 2, 12, tzinfo=timezone.utc)))
        self.assertIsNone(window({'kind': 'idle'}, datetime.now(timezone.utc)))
        self.assertEqual(job_name('uid', '2026-01-01'), job_name('uid', '2026-01-01'))
        self.assertNotEqual(job_name('uid', '2026-01-01'), job_name('other', '2026-01-01'))

    def test_dst_and_weekends(self):
        now = datetime(2026, 3, 29, 0, tzinfo=timezone.utc)
        self.assertEqual(window({'timeZone': 'Europe/Madrid', 'startHour': 1, 'endHour': 6}, now)[1], 14400)
        self.assertIsNone(window({'kind': 'weekends'}, datetime(2026, 11, 4, tzinfo=timezone.utc)))

    def test_export_preserves_bytes_and_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root/'source'; source.mkdir()
            (source/'work.musicxml').write_bytes(b'<score/>')
            self.assertEqual(export_local(source, root/'export'), 1)
            self.assertEqual((root/'export/work.musicxml').read_bytes(), b'<score/>')
            with self.assertRaises(FileExistsError): export_local(source, root/'export')
            with self.assertRaises(ValueError): export_local(source, source/'nested')
            (source/'link').symlink_to('/etc/passwd')
            with self.assertRaises(ValueError): export_local(source, root/'unsafe')

    def test_crds_match_emitted_kinds_and_checked_in_chart(self):
        self.assertEqual({c['spec']['names']['kind'] for c in crds()}, set(KINDS))
        self.assertEqual(list(yaml.safe_load_all(Path('charts/mnemosyne/crds/mnemosyne.yaml').read_text())), crds())
        for crd in crds():
            v = crd['spec']['versions'][0]
            self.assertIn('status', v['subresources'])
            self.assertTrue(v['additionalPrinterColumns'])


@unittest.skipUnless(shutil.which('helm'), 'helm unavailable')
class AddonChartTests(unittest.TestCase):
    def values(self):
        return {'addon': {'enabled': True, 'images': {
            role: {'digest': 'sha256:'+'a'*64} for role in ['controller','studio']},
            'key': {'secretName': 'atelier', 'ownerPublic': '00'*32}}}

    def render(self, values):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'values.yaml'; path.write_text(yaml.safe_dump(values))
            p = subprocess.run(['helm','template','test','charts/mnemosyne','-n','atelier','-f',str(path)],
                               capture_output=True,text=True)
            if p.returncode: raise ValueError(p.stderr)
            return list(yaml.safe_load_all(p.stdout))

    def test_portable_job_security_and_retention(self):
        docs = self.render(self.values())
        config = next(d for d in docs if d['kind']=='ConfigMap' and 'runtime.json' in d['data'])
        pod = json.loads(config['data']['runtime.json'])['pod']
        self.assertEqual(pod['nodeSelector'], {})
        self.assertIn('@sha256:',pod['containers'][0]['image'])
        self.assertTrue(pod['securityContext']['runAsNonRoot'])
        reader = next(d for d in docs if d['kind']=='ClusterRole')
        for rule in reader['rules']:
            self.assertNotIn('secrets', rule.get('resources', []))
            self.assertTrue(set(rule['verbs']) <= {'get','list','watch'})
        pvc = next(d for d in docs if d['kind']=='PersistentVolumeClaim')
        self.assertEqual(pvc['metadata']['annotations']['helm.sh/resource-policy'], 'keep')
        self.assertEqual(next(d for d in docs if d['kind']=='PriorityClass')['value'], -2147483648)

    def test_gallery_reads_only_and_history_needs_its_digest(self):
        values = self.values()
        values['addon'].update(gallery={'enabled': True},
                               history={'source': 'https://example.org/h.tar.gz', 'sha256': 'b' * 64})
        docs = self.render(values)
        gallery = next(d for d in docs if d['kind'] == 'Deployment' and d['metadata']['name'].endswith('-gallery'))
        spec = gallery['spec']['template']['spec']
        self.assertFalse(spec['automountServiceAccountToken'])
        self.assertTrue(next(v for v in spec['volumes'] if v['name'] == 'works')['persistentVolumeClaim']['readOnly'])
        self.assertTrue(spec['containers'][0]['volumeMounts'][0]['readOnly'])
        job = next(d for d in docs if d['kind'] == 'Job')
        self.assertIn('b' * 64, job['spec']['template']['spec']['containers'][0]['command'])
        config = next(d for d in docs if d['kind'] == 'ConfigMap' and 'runtime.json' in d['data'])
        self.assertIn('podAffinity', json.loads(config['data']['runtime.json'])['pod']['affinity'])
        values['addon']['history'] = {'source': 'https://example.org/h.tar.gz', 'sha256': ''}
        with self.assertRaises(ValueError):
            self.render(values)

    def test_reject_missing_digests_and_accidental_secret_inventory(self):
        values = self.values(); values['addon']['images']['studio']['digest'] = ''
        with self.assertRaises(ValueError): self.render(values)
        values = self.values(); values['addon']['inventory'] = [dict(apiVersion='v1',kind='Secret',resource='secrets')]
        with self.assertRaises(ValueError): self.render(values)


class ControllerTests(unittest.TestCase):
    def test_job_deadline_bounded_and_restart_identity_stable(self):
        from mnemosyne.operator.controller import make_job
        body = {'metadata': {'uid':'uid','name':'test','namespace':'atelier'},
                'spec': {'runtime': {'mode':'chamber','deadlineSeconds':900}}}
        runtime = {'pod': {'containers':[{'name':'studio','image':'test'}]}}
        job = make_job(body,runtime,'2026-01-01',120)
        self.assertEqual(job['spec']['activeDeadlineSeconds'],120)
        self.assertEqual(job['spec']['backoffLimit'],0)
        self.assertNotIn('env', runtime['pod']['containers'][0])
        self.assertEqual(make_job(body,runtime,'2026-01-01',120),job)


class TransportTests(unittest.TestCase):
    def test_loss_is_measured_per_work_and_detects_missing_rank(self):
        from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey
        from mnemosyne.weave import fountain
        from mnemosyne.operator.loss import check
        key = X25519PrivateKey.generate()
        encoder = fountain.Encoder(b'x'*500,256,key)
        self.assertGreater(encoder.k, 1)
        complete = [encoder.frame(i) for i in range(encoder.k)]
        self.assertTrue(check([complete, complete, complete], key)['loss_tolerance_verified'])
        self.assertFalse(check([[complete[0]]]*3,key)['loss_tolerance_verified'])

    def test_key_file_and_invalid_length(self):
        from mnemosyne.operator.keys import load
        with tempfile.TemporaryDirectory() as tmp:
            from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey
            owner = X25519PrivateKey.generate().public_key().public_bytes_raw().hex()
            path = Path(tmp)/'key';path.write_bytes(bytes(range(32)))
            self.assertEqual(load({'path':str(path),'ownerPublic':owner}).atelier.private_bytes_raw(),bytes(range(32)))
            path.write_bytes(b'bad')
            with self.assertRaises(ValueError): load({'path':str(path),'ownerPublic':owner})

    def test_vault_rejects_plain_http_before_reading_token(self):
        from mnemosyne.operator.keys import load
        with self.assertRaises(ValueError):
            load({'provider':'vault','vault':{'address':'http://example.test'}})

    def test_secret_archive_still_requires_explicit_restore_opt_in(self):
        from mnemosyne.state.collect import archive
        from mnemosyne.restore import read_archive
        # Synthetic fixture, never a live Kubernetes Secret.
        data = archive([{'apiVersion':'v1','kind':'Secret','metadata':{'name':'fixture','namespace':'test'},
                         'data':{'test':'Zml4dHVyZQ=='}}],include_secrets=True)
        with self.assertRaises(ValueError): read_archive(data)
        self.assertEqual(len(read_archive(data,include_secrets=True)),1)


class ReconcileTests(unittest.TestCase):
    def test_existing_night_is_never_created_again_after_restart(self):
        from types import SimpleNamespace as NS
        from mnemosyne.operator.controller import reconcile
        from unittest.mock import MagicMock
        body = {'metadata': {'uid':'uid','name':'atelier','namespace':'test','generation':1},
                'spec': {'runtime': {'window':{'kind':'always'}}}}
        now = datetime.now(timezone.utc)
        name = job_name('uid', str(now.date()))
        batch = MagicMock()
        batch.list_namespaced_job.return_value.items = [NS(metadata=NS(name=name),status=NS(succeeded=1,failed=0))]
        status = NS(status={})
        with patch('mnemosyne.operator.controller.connect'), patch('mnemosyne.operator.controller.client.BatchV1Api',return_value=batch), \
             patch('mnemosyne.operator.controller.Path.read_text',return_value='{}'), \
             patch.dict('os.environ',{'MNEMO_RUNTIME':'unused'}):
            reconcile(body,status)
        batch.create_namespaced_job.assert_not_called()
        self.assertEqual(status.status['phase'],'JobSucceeded')

    def test_owner_suspend_stops_active_job(self):
        from types import SimpleNamespace as NS
        from mnemosyne.operator.controller import reconcile
        from unittest.mock import MagicMock
        body = {'metadata':{'name':'atelier','namespace':'test'},'spec':{'runtime':{'suspend':True}}}
        batch=MagicMock()
        batch.list_namespaced_job.return_value.items=[NS(metadata=NS(name='job'),status=NS(succeeded=0,failed=0),spec=NS(suspend=False))]
        status=NS(status={})
        with patch('mnemosyne.operator.controller.connect'),patch('mnemosyne.operator.controller.client.BatchV1Api',return_value=batch), \
             patch('mnemosyne.operator.controller.Path.read_text',return_value='{}'), \
             patch.dict('os.environ',{'MNEMO_RUNTIME':'unused'}):
            reconcile(body,status)
        batch.patch_namespaced_job.assert_called_once_with('job','test',{'spec':{'suspend':True}})
        self.assertEqual(status.status['phase'],'Suspended')


class LineageResumeTests(unittest.TestCase):
    def test_new_pvc_can_resume_restored_crs(self):
        from mnemosyne.lineage import Lineage
        from mnemosyne.atelier import Atelier, KINDS
        from mnemosyne.operator.kube import restored_lineage
        from unittest.mock import MagicMock
        life=Lineage('resume',datetime(2025,1,1))
        with tempfile.TemporaryDirectory() as tmp:
            atelier=Atelier('resume',Path(tmp));atelier.lineage(life)
            lookup={(KINDS[o['kind']],o['metadata']['name']):o for o in atelier.objects}
            custom=MagicMock()
            custom.get_namespaced_custom_object.side_effect=lambda g,v,ns,p,n: lookup[p,n]
            with patch('kubernetes.client.CustomObjectsApi',return_value=custom):
                self.assertEqual(restored_lineage(None,'test','resume'),life.state())
