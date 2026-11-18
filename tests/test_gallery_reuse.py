import os
import tempfile
import unittest
from pathlib import Path

from mnemosyne.gallery import reuse
from mnemosyne.viewer import copy


class ReuseTests(unittest.TestCase):
    def test_media_is_linked_and_pages_are_not(self):
        with tempfile.TemporaryDirectory() as d:
            site, fresh = Path(d)/'current', Path(d)/'current.next'
            (site/'audio/w').mkdir(parents=True)
            (site/'audio/w/work.mp3').write_bytes(b'x' * 10)
            (site/'index.html').write_text('<p>old</p>')
            reuse(site, fresh)
            self.assertEqual((fresh/'audio/w/work.mp3').stat().st_ino, (site/'audio/w/work.mp3').stat().st_ino)
            self.assertFalse((fresh/'index.html').exists())

    def test_changed_file_does_not_write_through_the_link(self):
        with tempfile.TemporaryDirectory() as d:
            site, fresh = Path(d)/'current', Path(d)/'current.next'
            site.mkdir()
            (site/'score.pdf').write_bytes(b'old')
            reuse(site, fresh)
            source = Path(d)/'new.pdf'
            source.write_bytes(b'newer content')
            copy(source, fresh/'score.pdf')
            self.assertEqual((site/'score.pdf').read_bytes(), b'old')
            self.assertEqual((fresh/'score.pdf').read_bytes(), b'newer content')

    def test_no_previous_site(self):
        with tempfile.TemporaryDirectory() as d:
            reuse(Path(d)/'missing', Path(d)/'fresh')
            self.assertFalse((Path(d)/'fresh').exists())


if __name__ == '__main__':
    unittest.main()
