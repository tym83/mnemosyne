"""A writer's night: idea, school, drafts held to their form, verdict, the Translator."""
import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from mnemosyne.artist import Statement
from mnemosyne.lineage import Lineage
from mnemosyne.writing import translator
from mnemosyne.writing.night import Draft, Method, Reading, WriterNight
from mnemosyne.writing.schools import SCHOOLS

HAIKU = 'Старый пруд молчит.\nПрыгнула в воду лягушка.\nВсплеск над тишиной.'
BAD = 'Пруд.\nЛягушка.'


def statement():
    return Statement(**{k: [] if f.annotation == list[str] else 'idea' for k, f in Statement.model_fields.items()})


def writer_life(language):
    life = Lineage('leonia', datetime(2025, 1, 1), seed=2)
    a = next(a for a in life.artists if a.art == 'literature')
    a.portrait, a.language = 'Fixture portrait', language
    return life, a


class WriterNightTests(unittest.TestCase):
    def run_night(self, language, texts):
        life, a = writer_life(language)
        calls = []
        texts = list(texts)

        def ask(system, prompt, schema, step, **kw):
            calls.append((step, system))
            if schema is Method:
                return Method(kind='school', school='haiku', reason='fixture')
            if schema is Draft:
                return Draft(title='t', text='\n\n'.join([texts.pop(0)] * 3), diary='{тихо|ясно}')
            if schema is Reading:
                return Reading(verdict='accept', reasons='r', corrections=[], matters=False, quality=.7)
            if schema is translator.Translation:
                return translator.Translation(text='перевод')
            raise AssertionError(schema)
        with tempfile.TemporaryDirectory() as tmp:
            night = WriterNight(life, a.id, Path(tmp)/'w')
            with patch('mnemosyne.artist.statement', return_value=(statement(), [{'interrogation': {'verdict': 'accept'}}])), \
                 patch.object(night.writer, 'ask', side_effect=ask), \
                 patch('mnemosyne.literature.Writer.ask', side_effect=ask):
                record = night.run()
            files = sorted(p.name for p in Path(tmp, 'w').iterdir())
        return record, calls, a, files

    def test_form_problems_go_back_to_the_writer_until_the_form_holds(self):
        record, calls, a, files = self.run_night('ru', [BAD, HAIKU])
        self.assertEqual(record['status'], 'accepted')
        self.assertEqual([s for s, _ in calls if s.startswith('draft')], ['draft:0:0', 'draft:0:1'])
        self.assertEqual(record['drafts'][0]['form_problems'], [])
        self.assertIsNone(record['translation'])
        self.assertEqual(a.catalogue[-1]['school'], 'haiku')
        self.assertFalse(a.catalogue[-1]['synthetic'])

    def test_the_translator_renders_other_languages_into_russian(self):
        record, calls, a, files = self.run_night('ja', [HAIKU])
        self.assertEqual(record['translation'], 'перевод')
        system = next(s for step, s in calls if step == 'translate:work')
        self.assertIn('Переводчик', system)
        self.assertIn(f'{record["opus"]}.ru.txt', files)

    def test_every_school_reads_its_own_frame(self):
        import random
        for name, school in SCHOOLS.items():
            frame = school.skeleton(school.EXAMPLE_PLAN, random.Random(3))
            self.assertIsInstance(school.check('', frame, 'ru'), list, name)
            self.assertIn(school.KIND, ('poetry', 'prose'))
            self.assertTrue(school.RULES and school.EXAMPLE_PLAN['school'] == name, name)

    def test_the_prose_traditions_are_schools_with_names(self):
        from mnemosyne.viewer import SCHOOL_RU
        for key in ('psychological_realism', 'polyphony', 'magical_realism', 'stream_of_consciousness', 'skaz',
                    'platonov', 'faulkner', 'epistolary', 'nouveau_roman', 'gothic'):
            self.assertEqual(SCHOOLS[key].KIND, 'prose', key)
            self.assertIn(key, SCHOOL_RU, key)

    def test_a_writer_founds_a_school_and_writes_in_it_the_same_night(self):
        from mnemosyne.writing import founding, poetics
        from mnemosyne.writing.founding import Judgement, Poetics
        life, a = writer_life('it')
        verdicts = ['rewrite', 'accept']
        story = ' '.join(['parola'] * 300)

        def ask(system, prompt, schema, step, **kw):
            if schema is Method:
                return Method(kind='invent_school', school='Realismo della premura', reason='nessuna scuola regge')
            if schema is Poetics:
                fields = {k: 'testo' for k in Poetics.model_fields}
                return Poetics(**{**fields, 'name': 'Realismo della premura', 'manifesto': ['uno', 'due'],
                                  'forbidden': ['spiegare'], 'markers': ['oggetti'], 'kind': 'prose',
                                  'min_words': 200, 'max_words': 800})
            if schema is Judgement:
                v = verdicts.pop(0)
                return Judgement(verdict=v, renaming_of='minimalismo' if v == 'rewrite' else '', reasons='r',
                                 corrections=['più mondo'] if v == 'rewrite' else [])
            if schema is Draft:
                return Draft(title='La sedia', text=story, diary='d')
            if schema is Reading:
                return Reading(verdict='accept', reasons='r', corrections=[], matters=True, quality=.7)
            if schema is translator.Translation:
                return translator.Translation(text='перевод')
            raise AssertionError(schema)
        with tempfile.TemporaryDirectory() as tmp:
            night = WriterNight(life, a.id, Path(tmp)/'w')
            with patch('mnemosyne.artist.statement', return_value=(statement(), [{'interrogation': {'verdict': 'accept'}}])), \
                 patch.object(night.writer, 'ask', side_effect=ask), \
                 patch('mnemosyne.literature.Writer.ask', side_effect=ask):
                record = night.run()
        key = a.catalogue[-1]['school']
        self.assertEqual(record['status'], 'accepted')
        self.assertTrue(key.startswith('born-'))
        self.assertNotIn('leonia', key)
        self.assertEqual(life.schools[key]['art'], 'literature')
        self.assertEqual(len(record['school_birth']['attempts']), 2)
        self.assertIn('school_birth', [e['kind'] for e in life.events])
        self.assertEqual(poetics.load(key)['name'], 'Realismo della premura')
        self.assertIn(key, founding.schools(life))
        # The music side never mistakes a born literature school for a grammar.
        from mnemosyne.music.school_birth import register_all
        register_all(life.schools)

    def test_an_unborn_school_leaves_the_story_to_the_nearest_known_school(self):
        from mnemosyne.writing.founding import Judgement, Poetics
        life, a = writer_life('ru')

        def ask(system, prompt, schema, step, **kw):
            if schema is Method:
                return Method(kind='invent_school', school='Новая', reason='r') if step == 'method' else \
                    Method(kind='school', school='haiku', reason='ближе всего')
            if schema is Poetics:
                fields = {k: 'текст' for k in Poetics.model_fields}
                return Poetics(**{**fields, 'manifesto': ['раз'], 'forbidden': [], 'markers': [], 'kind': 'prose',
                                  'min_words': 100, 'max_words': 500})
            if schema is Judgement:
                return Judgement(verdict='rewrite', renaming_of='реализм', reasons='r', corrections=['c'])
            if schema is Draft:
                return Draft(title='t', text='\n\n'.join([HAIKU] * 3), diary='d')
            if schema is Reading:
                return Reading(verdict='accept', reasons='r', corrections=[], matters=False, quality=.7)
            raise AssertionError(schema)
        with tempfile.TemporaryDirectory() as tmp:
            night = WriterNight(life, a.id, Path(tmp)/'w')
            with patch('mnemosyne.artist.statement', return_value=(statement(), [{'interrogation': {'verdict': 'accept'}}])), \
                 patch.object(night.writer, 'ask', side_effect=ask), \
                 patch('mnemosyne.literature.Writer.ask', side_effect=ask):
                record = night.run()
        self.assertEqual(record['status'], 'accepted')
        self.assertTrue(record['method']['after_unborn'])
        self.assertEqual(a.catalogue[-1]['school'], 'haiku')
        self.assertEqual(life.school_attempts[-1]['status'], 'unborn')
        self.assertEqual(life.schools, {})

    def test_born_school_form_counts_cjk_words(self):
        from mnemosyne.writing.founding import BornSchool, words
        self.assertEqual(words('听完一句拒绝'), 3)
        school = BornSchool('born-x', {'poetics': {'kind': 'prose', 'min_words': 100, 'max_words': 300}})
        frame = school.skeleton({}, None)
        self.assertTrue(school.check('слово ' * 10, frame, 'ru'))
        self.assertEqual(school.check('слово ' * 150, frame, 'ru'), [])


class FormTests(unittest.TestCase):
    def test_chastushka_rhyme_and_pavic_references(self):
        import random
        frame = {'stanzas': 1, 'refrain': False}
        good = 'Я на горке постояла,\nПоглядела на реку,\nМного песен я не знала,\nА теперь их нареку.'
        self.assertEqual(SCHOOLS['chastushka'].check(good, frame, 'ru'), [])
        lexicon = 'ВЕТЕР\nОн дует → РЕКА\n\nРЕКА\nОна течёт → ВЕТЕР'
        self.assertEqual(SCHOOLS['pavic'].check(lexicon, {'entries': 2, 'references': [1, 1]}, 'ru'), [])
        broken = 'РЕКА\nтечёт → МОСТ\n\nВЕТЕР\nдует'
        problems = SCHOOLS['pavic'].check(broken, {'entries': 2, 'references': [1, 1]}, 'ru')
        self.assertTrue(any('alphabetical' in p for p in problems))
        self.assertTrue(any('МОСТ' in p for p in problems))


if __name__ == '__main__':
    unittest.main()
