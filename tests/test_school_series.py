"""Mixed-capacity real scores through the retained registry and restore CLI API."""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest

from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey
from mnemosyne.music.schools import SCHOOLS
from mnemosyne.restore import recover_works
from mnemosyne.state.collect import archive
from mnemosyne.weave import DecodeError, fountain, payload, registry, schools, school_series, surface
from mnemosyne.weave.school_audit import plan_for


class SeriesTests(unittest.TestCase):
    def test_mixed_schools_restore_and_authenticated_context(self):
        key = X25519PrivateKey.generate()
        data = archive([{'apiVersion':'v1', 'kind':'Namespace', 'metadata':{'name':'leonia'}}])
        envelope = payload.seal(data, key.public_key(), context=fountain.DOMAIN)
        encoder = fountain.Encoder(envelope, 120, key)
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            works = directory/'works'; works.mkdir()
            roots = []
            for name in ('additive', 'drone'):
                plan = plan_for(name)
                score = SCHOOLS[name].compose(plan, plan['seed'])
                path = directory/(name+'.musicxml'); score.write('musicxml', fp=path)
                root = schools.prepare(surface.read(path), name)
                roots.append(registry.mark(root, (name, 'dynamics-fountain', '2')))
            # Repair-only recovery with different-sized actual musical surfaces.
            for index in range(encoder.k, 2*encoder.k+32):
                frames = [encoder.frame(index), encoder.frame(index+1000)]
                root = school_series.encode_many(roots[index%2], frames, key)
                path = works/f'{index}.musicxml'; surface.write(root, path)
                self.assertEqual(registry.decode(path,key).frame, frames)
            result, objects, report = recover_works(works,key)
            self.assertEqual(result,data)
            self.assertEqual(len(objects),1)
            self.assertEqual(report['rejected'],[])
            for change in ('note','descriptor','padding'):
                bad = deepcopy(root)
                if change=='note': bad.find('.//pitch/octave').text='9'
                elif change=='descriptor':
                    bad.find('.//miscellaneous-field').text='{}'
                else:
                    block = bytearray(schools.decode(bad)); block[-13] ^= 1
                    bad = schools.encode(bad, bytes(block))
                path = directory/'bad.musicxml'; surface.write(bad,path)
                with self.assertRaises(DecodeError): registry.decode(path,key)

    def test_v1_registry_uses_retained_dynamics(self):
        key = X25519PrivateKey.generate()
        plan = plan_for('serial')
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'score.musicxml'
            SCHOOLS['serial'].compose(plan,plan['seed']).write('musicxml',fp=path)
            root = registry.mark(schools.prepare(surface.read(path),'serial'),
                                 ('serial','dynamics-fountain','1'))
            env = payload.seal(b'old work',key.public_key(),context=fountain.DOMAIN)
            enc = fountain.Encoder(env, schools.capacity(root)-12,key)
            surface.write(schools.weave_fountain(root,enc,0,key),path)
            self.assertEqual(registry.decode(path,key).frame,enc.frame(0))
            misc=root.find('./identification/miscellaneous')
            misc.remove(misc.find('miscellaneous-field'))
            surface.write(schools.weave_fountain(root,enc,0,key),path)
            self.assertEqual(registry.decode(path,key).frame,enc.frame(0))


if __name__=='__main__': unittest.main()
