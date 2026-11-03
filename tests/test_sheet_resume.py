import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scheherazade.drawing.sheets import draw


class SheetResume(unittest.TestCase):
    def test_existing_draft_and_plate_skip_workshop(self):
        with tempfile.TemporaryDirectory() as tmp, patch("scheherazade.drawing.sheets.kube") as kube:
            for name in ("sheet01_draft1", "sheet01_plate"):
                png = Path(tmp) / f"{name}.png"
                png.write_bytes(b"existing image")
                png.with_suffix(".py").write_text("original")
                self.assertEqual(draw("original", png), "")
            kube.assert_not_called()

    def test_changed_script_failure_then_resume(self):
        with tempfile.TemporaryDirectory() as tmp:
            png = Path(tmp) / "sheet01_draft1.png"
            png.write_bytes(b"old image")
            png.with_suffix(".py").write_text("old")
            with patch("scheherazade.drawing.sheets.kube",
                       return_value=subprocess.CompletedProcess([], 1, stdout="render failed")) as kube:
                self.assertEqual(draw("new", png), "render failed")
                self.assertTrue(kube.called)
            self.assertEqual(png.with_suffix(".render-state").read_text(), "pending")

            def render(*args, **kwargs):
                if args[0] == "cp" and args[-1] == str(png):
                    png.write_bytes(b"new image")
                return subprocess.CompletedProcess([], 0, stdout="")

            with patch("scheherazade.drawing.sheets.kube", side_effect=render) as kube:
                self.assertEqual(draw("new", png), "")
                self.assertTrue(kube.called)
                kube.reset_mock()
                self.assertEqual(draw("new", png), "")
                kube.assert_not_called()
            self.assertEqual(png.read_bytes(), b"new image")

    def test_missing_png_renders(self):
        with tempfile.TemporaryDirectory() as tmp, patch("scheherazade.drawing.sheets.kube",
                return_value=subprocess.CompletedProcess([], 1, stdout="no image")) as kube:
            png = Path(tmp) / "sheet01_draft1.png"
            png.with_suffix(".py").write_text("original")
            self.assertEqual(draw("original", png), "no image")
            self.assertTrue(kube.called)


if __name__ == "__main__":
    unittest.main()
