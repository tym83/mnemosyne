import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scheherazade.drawing.sheets import draw


class SheetResume(unittest.TestCase):
    def test_fingerprint_resume_and_metadata_change(self):
        with tempfile.TemporaryDirectory() as tmp:
            png = Path(tmp) / 'draft.png'

            def workshop(*args, **kwargs):
                if args[0] == 'cp' and args[1].startswith('studio-1:'):
                    Path(args[2]).write_bytes(b'new image')
                return subprocess.CompletedProcess([], 0, stdout='', stderr='')

            with patch('scheherazade.drawing.sheets.kube', side_effect=workshop) as kube:
                self.assertEqual(draw('original', png), '')
                kube.reset_mock()
                self.assertEqual(draw('original', png), '')
                kube.assert_not_called()
                self.assertEqual(draw('original', png, title='Changed'), '')
                self.assertTrue(kube.called)

    def test_legacy_image_does_not_skip_and_failure_stays_pending(self):
        with tempfile.TemporaryDirectory() as tmp:
            png = Path(tmp) / 'draft.png'
            png.write_bytes(b'old image')
            png.with_suffix('.py').write_text('original')
            with patch('scheherazade.drawing.sheets.kube', return_value=
                       subprocess.CompletedProcess([], 1, stdout='render failed', stderr='')):
                self.assertEqual(draw('original', png), 'render failed')
            self.assertEqual(png.with_suffix('.render-state').read_text(), 'pending')
            self.assertEqual(png.read_bytes(), b'old image')

    def test_failed_postprocess_does_not_copy_stale_image(self):
        with tempfile.TemporaryDirectory() as tmp:
            png = Path(tmp) / 'draft.png'

            def workshop(*args, **kwargs):
                if '/work/venv/bin/python' in args:
                    return subprocess.CompletedProcess([], 1, stdout='etch failed', stderr='')
                return subprocess.CompletedProcess([], 0, stdout='', stderr='')

            with patch('scheherazade.drawing.sheets.kube', side_effect=workshop):
                self.assertEqual(draw('original', png), 'etch failed')
            self.assertFalse(png.exists())
            self.assertEqual(png.with_suffix('.render-state').read_text(), 'pending')


if __name__ == '__main__':
    unittest.main()
