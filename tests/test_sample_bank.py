"""Sample downloads wait out a host's passing outage and fail fast on a missing file."""
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

from mnemosyne.music import sample_bank


class OpenedTests(unittest.TestCase):
    def test_a_passing_outage_is_waited_out(self):
        calls = []

        def flaky(url, timeout):
            calls.append(url)
            if len(calls) < 3:
                raise HTTPError(url, 503, 'Service Unavailable', {}, None)
            return 'response'

        with patch.object(sample_bank, 'urlopen', flaky), patch.object(sample_bank.time, 'sleep', lambda _: None):
            self.assertEqual(sample_bank.opened('https://example/x'), 'response')
        self.assertEqual(len(calls), 3)

    def test_a_missing_file_is_not_retried(self):
        calls = []

        def missing(url, timeout):
            calls.append(url)
            raise HTTPError(url, 404, 'Not Found', {}, None)

        with patch.object(sample_bank, 'urlopen', missing):
            with self.assertRaises(HTTPError):
                sample_bank.opened('https://example/x')
        self.assertEqual(len(calls), 1)
