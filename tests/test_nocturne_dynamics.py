from copy import deepcopy
import unittest
import xml.etree.ElementTree as ET
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey
from mnemosyne.weave import DecodeError, fountain, payload, registry, schools, school_series
from mnemosyne.weave.nocturne_dynamics import prepare, IDENTITY


class NocturneDynamicsTests(unittest.TestCase):
    def test_phrase_staff_rest_and_authenticated_roundtrip(self):
        root = ET.fromstring('''<score-partwise><part id="P1"><measure number="1">
        <attributes><divisions>4</divisions></attributes>
        <direction><direction-type><dynamics><p/></dynamics></direction-type></direction>
        <direction><direction-type><wedge type="crescendo"/></direction-type></direction>
        <note><pitch><step>C</step><octave>4</octave></pitch><duration>16</duration><staff>1</staff></note>
        <direction><direction-type><wedge type="stop"/></direction-type></direction>
        <note><rest/><duration>4</duration></note>
        <backup><duration>20</duration></backup>
        <note><pitch><step>C</step><octave>3</octave></pitch><duration>16</duration><staff>2</staff></note>
        </measure></part></score-partwise>''')
        prepared = prepare(root)
        values = [opts[0]+1.875 for _,opts in schools.slots(prepared)]
        self.assertEqual(values[:8], [35+1.5*i for i in range(8)])
        self.assertEqual(values[8:], values[:8])
        self.assertEqual(len(list(root.iter('direction'))), 3)
        self.assertEqual([d.findtext('staff') for d in prepared.iter('direction') if d.get('id')], ['1']*8+['2']*8)
        # Larger real-shaped surface for an authenticated fountain frame.
        part = root.find('part')
        for i in range(40): part.append(deepcopy(part[0]))
        prepared = registry.mark(prepare(root), IDENTITY)
        key = X25519PrivateKey.generate()
        env = payload.seal(b'nocturne', key.public_key(), context=fountain.DOMAIN)
        frame = fountain.Encoder(env, 120, key).frame(0)
        woven = school_series.encode_many(prepared, [frame], key)
        self.assertEqual(registry.DECODERS[IDENTITY](woven,key).frame, [frame])
        self.assertTrue(all(abs(float(s.get('dynamics'))-(o[0]+1.875)) <= 1.875 for s,o in schools.slots(woven)))
        for xpath in ('.//pitch/octave', './/rest/../duration', './/direction[@id]/staff'):
            bad = deepcopy(woven); bad.find(xpath).text = '9'
            with self.assertRaises(DecodeError): registry.DECODERS[IDENTITY](bad,key)


if __name__ == '__main__': unittest.main()
