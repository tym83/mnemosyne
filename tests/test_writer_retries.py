import os
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from pydantic import BaseModel

from scheherazade.literature import Writer, _transient


class Answer(BaseModel):
    text: str


class WriterRetries(unittest.TestCase):
    def test_capacity_then_success_and_cache(self):
        notebook = []
        writer = Writer(notebook, backend="codex")
        error = RuntimeError("ERROR: Selected model is at capacity. Please try a different model.")
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, WRITER_CACHE=tmp), \
                patch.object(writer, "_codex", side_effect=[error, error, ('{"text":"ok"}', {})]) as backend, \
                patch("scheherazade.literature.time.sleep") as sleep:
            self.assertEqual(writer.ask("", "", Answer, "test").text, "ok")
            self.assertEqual(writer.ask("", "", Answer, "test").text, "ok")
            self.assertEqual(backend.call_count, 3)
            self.assertEqual([c.args[0] for c in sleep.call_args_list], [60, 120])
            self.assertEqual([e["wait_seconds"] for e in notebook[:2]], [60, 120])
            self.assertTrue(notebook[-1]["cached"])

    def test_broken_answers_have_separate_budget(self):
        writer = Writer([], backend="codex")
        # Error words in a malformed answer are not a backend outage.
        bad = ('{"wrong":"network timeout at capacity"}', {})
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, WRITER_CACHE=tmp), \
                patch.object(writer, "_codex", side_effect=[bad, TimeoutError(), bad, bad]) as backend, \
                patch("scheherazade.literature.time.sleep") as sleep:
            with self.assertRaises(RuntimeError):
                writer.ask("", "", Answer, "test")
            self.assertEqual(backend.call_count, 4)
            sleep.assert_called_once_with(60)

    def test_twelve_hour_limit_and_half_hour_cap(self):
        now, waits = [0], []

        def sleep(seconds):
            waits.append(seconds)
            now[0] += seconds

        writer = Writer([], backend="codex")
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, WRITER_CACHE=tmp), \
                patch.object(writer, "_codex", side_effect=RuntimeError("rate limit")), \
                patch("scheherazade.literature.time.monotonic", side_effect=lambda: now[0]), \
                patch("scheherazade.literature.time.sleep", side_effect=sleep), patch("builtins.print"):
            with self.assertRaisesRegex(RuntimeError, "rate limit"):
                writer.ask("", "", Answer, "test")
        self.assertEqual(sum(waits), 12 * 3600)
        self.assertEqual(max(waits), 30 * 60)
        self.assertEqual(waits[:3], [60, 120, 240])

    def test_transient_types(self):
        for error in (ConnectionError(), subprocess.TimeoutExpired("codex", 3600),
                      RuntimeError("Too many requests"), RuntimeError("network unreachable")):
            self.assertTrue(_transient(error))
        self.assertFalse(_transient(RuntimeError("authentication failed")))


if __name__ == "__main__":
    unittest.main()
