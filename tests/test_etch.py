import tempfile
import unittest
from pathlib import Path

from PIL import Image, ImageDraw

from scheherazade.drawing.etch import difference
from scheherazade.drawing.sheets import kit_reference


class PlateComparison(unittest.TestCase):
    def test_same_image_and_large_composition_change(self):
        with tempfile.TemporaryDirectory() as tmp:
            a, b = Path(tmp) / 'a.png', Path(tmp) / 'b.png'
            im = Image.new('RGB', (600, 400), 'white')
            ImageDraw.Draw(im).rectangle((80, 70, 220, 300), fill='black')
            im.save(a)
            im.save(b)
            self.assertTrue(difference(a, b)['barely_changed'])
            im = Image.new('RGB', (600, 400), 'white')
            ImageDraw.Draw(im).rectangle((310, 70, 450, 300), fill='black')
            im.save(b)
            self.assertFalse(difference(a, b)['barely_changed'])

    def test_kit_reference_exposes_language(self):
        ref = kit_reference()
        self.assertIn('etching | aquatint | ink_line', ref)
        self.assertIn('1/15', ref)
        self.assertIn('Faceless', ref)
