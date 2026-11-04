"""Compatibility of injected sources and evidence for channel limits."""
import json
import random
import unittest

from test_music_schools import fingerprint, PLANS
from mnemosyne.music.schools import SCHOOLS
from mnemosyne.music.schools.choices import SeededChoices
from mnemosyne.weave.school_capacity import SINGLE, SingleChoice, bound, support


class ChoiceTests(unittest.TestCase):
    def test_all_schools_match_original_random_source(self):
        for name, school in SCHOOLS.items():
            with self.subTest(school=name):
                plan = json.loads((PLANS / f'{name}.json').read_text())
                seed = plan['seed']
                expected = school.compose(plan, seed, choices=random.Random(seed))
                actual = school.compose(plan, seed)
                self.assertEqual(fingerprint(expected), fingerprint(actual))

    def test_injection_overrides_seed_even_for_falsey_source(self):
        class FalseySource(SeededChoices):
            def __bool__(self):
                return False
        plan = json.loads((PLANS / 'serial.json').read_text())
        school = SCHOOLS['serial']
        self.assertEqual(fingerprint(school.compose(plan, 0, choices=FalseySource(42))),
                         fingerprint(school.compose(plan, 42)))

    def test_single_choice_support_survives_musicxml(self):
        for name, count in SINGLE.items():
            with self.subTest(school=name):
                plan = json.loads((PLANS / f'{name}.json').read_text())
                self.assertEqual(support(name, plan), count)
                self.assertLess(count, 256)

    def test_single_choice_auditor_rejects_extra_draws(self):
        source = SingleChoice(0)
        source.choice([0, 1])
        with self.assertRaises(ValueError):
            source.choice([0, 1])

    def test_fixed_motif_cannot_gain_capacity_by_lengthening(self):
        plan = json.loads((PLANS / 'serial.json').read_text())
        original = bound('serial', plan)
        plan['duration'] *= 100
        self.assertEqual(bound('serial', plan), original)
        self.assertLess(original, 29)


if __name__ == '__main__':
    unittest.main()
