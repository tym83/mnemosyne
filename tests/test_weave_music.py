import copy
from pathlib import Path
import tempfile
import unittest
import xml.etree.ElementTree as ET

from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey
from mnemosyne.weave import DecodeError, frames, payload, surface
from mnemosyne.weave.nocturne import decode, encode


def fixture():
    root = ET.Element('score-partwise')
    part = ET.SubElement(root, 'part', id='P1')
    for i in range(96):
        m = ET.SubElement(part, 'measure', number=str(i+1))
        if i == 0:
            a = ET.SubElement(m, 'attributes')
            ET.SubElement(a, 'divisions').text = '120'
        m.extend(surface.notes((('A', 0, 2), ('E', 0, 3), ('G', 0, 3)), 120, 120, '3'))
    return root


class SurfaceTests(unittest.TestCase):
    def test_all_options_reconstruct_and_preserve_context(self):
        root = fixture()
        original = surface.context(root)
        for m, ns, options, _, div in surface.slots(root):
            pcs = {surface.pitch(n)[:2] for n in ns}
            bass = min(surface.midi(surface.pitch(n)) for n in ns)
            for ps in options:
                self.assertEqual({p[:2] for p in ps}, pcs)
                self.assertEqual(surface.midi(ps[0]), bass)
                self.assertLessEqual(surface.midi(ps[-1])-bass, 16)
        for byte in (0, 1, 127, 255):
            block = bytes([byte])*surface.capacity(root)
            changed = surface.encode(root, block)
            self.assertEqual(surface.decode(changed), block)
            self.assertEqual(surface.context(changed), original)

    def test_multipart_musicxml_only_full_recovery(self):
        key = X25519PrivateKey.generate()
        data = b'{"kind":"Namespace","metadata":{"name":"shop"}}'
        envelope = payload.seal(data, key.public_key(), context=frames.DOMAIN)
        root = fixture()
        chunk = surface.capacity(root)-frames.OVERHEAD
        count = (len(envelope)+chunk-1)//chunk
        recovered = []
        with tempfile.TemporaryDirectory() as d:
            source, output = Path(d)/'source.xml', Path(d)/'work.musicxml'
            surface.write(root, source)
            for i in range(count):
                encode(source, output, envelope, i, key)
                # Decoder has no source, manifest, payload size or ciphertext.
                recovered.append(decode(output, key))
            self.assertEqual(frames.assemble(recovered[::-1], key), data)
            for bad in (recovered[:-1], recovered + recovered[:1]):
                with self.assertRaises(DecodeError):
                    frames.assemble(bad, key)
            with self.assertRaises(DecodeError):
                decode(output, X25519PrivateKey.generate())

    def test_tampering_in_carrier_noncarrier_and_header(self):
        key = X25519PrivateKey.generate()
        root = fixture()
        block = frames.pack(b'x'*50, 0, surface.capacity(root), key, surface.context(root))
        encoded = surface.encode(root, block)
        with tempfile.TemporaryDirectory() as d:
            path = Path(d)/'tampered.xml'
            for mode in ('note', 'duration', 'form', 'choice'):
                changed = copy.deepcopy(encoded)
                if mode == 'note':
                    changed.find('.//pitch/step').text = 'B'
                elif mode == 'duration':
                    changed.find('.//duration').text = '30'
                elif mode == 'form':
                    changed.find('.//measure').set('number', '99')
                else:
                    m, ns, opts, digit, div = surface.slots(changed)[0]
                    ps = opts[(digit//2+1) % len(opts)]
                    surface.replace(m, ns, surface.notes(ps, div, div, '3'))
                surface.write(changed, path)
                with self.assertRaises(DecodeError, msg=mode):
                    decode(path, key)
        for i in range(len(block)):
            bad = bytearray(block)
            bad[i] ^= 1
            with self.assertRaises(DecodeError):
                frames.unpack(bytes(bad), key, surface.context(root))

    def test_capacity_and_frame_limits(self):
        key = X25519PrivateKey.generate()
        for capacity, index in ((20, 0), (21, 255), (21, -1)):
            with self.assertRaises(ValueError):
                frames.pack(b'x'*100, index, capacity, key, b'')
        with self.assertRaises(DecodeError):
            frames.assemble([], key)

    def test_nocturne_invariants_when_available(self):
        path = Path('out/works/music/nocturne/p02_000.xml')
        if not path.exists():
            self.skipTest('generated nocturne unavailable')
        from music21 import converter, chord
        root = surface.read(path)
        changed = surface.encode(root, bytes([173])*surface.capacity(root))
        self.assertEqual(surface.context(root), surface.context(changed))
        with tempfile.TemporaryDirectory() as d:
            out = Path(d)/'encoded.musicxml'
            surface.write(changed, out)
            before, after = converter.parse(str(path)), converter.parse(str(out))
            for part_a, part_b in zip(before.parts, after.parts):
                a, b = part_a.flatten(), part_b.flatten()
                for beat in range(156):
                    def active(s):
                        return [p for n in s.notes if n.offset <= beat < n.offset+n.quarterLength for p in n.pitches]
                    pa, pb = active(a), active(b)
                    self.assertEqual({p.pitchClass for p in pa}, {p.pitchClass for p in pb})
                    if pa:
                        self.assertEqual(min(p.midi for p in pa), min(p.midi for p in pb))
                        ca, cb = chord.Chord(pa), chord.Chord(pb)
                        self.assertEqual((ca.root().pitchClass, ca.quality), (cb.root().pitchClass, cb.quality))


if __name__ == '__main__':
    unittest.main()
