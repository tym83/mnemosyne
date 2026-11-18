"""The Lexicon: entities and typed relations, linking by aliases, stale paragraphs revised into new editions."""
import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from mnemosyne import lexicon
from mnemosyne.lexicon import Index, Paragraph, Thing, Things
from mnemosyne.lineage import Lineage
from mnemosyne.viewer import Atelier, lex_page, site

TALE = 'Ну, значит, пришёл к нам в слободу один человек, и стал он ключи ковать без замков. Слобода смеялась.'


class Pen:
    """A mocked lexicographer: says what it was asked, cites its sources and one source it does not have."""
    calls = []

    def __init__(self, nb):
        pass

    def ask(self, system, prompt, schema, step):
        Pen.calls.append(step)
        if schema is Things:
            return Things(items=[Thing(name='Слобода', kind='place', aliases=['слободу'], gloss='Место, где куют ключи.')])
        if schema is Paragraph:
            ids = [l[1:].split(']')[0] for l in prompt.splitlines() if l.startswith('[') and ':' in l]
            return Paragraph(text=f'Абзац {len(Pen.calls)} о сказе и о Вере Тиховой. '
                                  + ' '.join(f'[{i}]' for i in ids) + ' [work:nowhere]')
        raise AssertionError(schema)


def atelier():
    life = Lineage('leonia', datetime(2025, 1, 1), seed=2)
    writer = next(a for a in life.artists if a.art == 'literature')
    composer = next(a for a in life.artists if a.art == 'music')
    writer.name, composer.name = 'Анна Лескова', 'Вера Тихова'
    composer.teachers = []
    writer.teachers = [composer.id]
    w = life._work(writer, observation=dict(feature=[.5] * 4, novelty=1, quality=.8, verdict='accept'))
    w.update(school='skaz', title='Ключи', text=TALE, idea='Замысел о ключах без замков')
    life.reception.register(writer, w)
    critic = next(c for c in life.reception.critics if c['voice'] == 'scholarly')
    review = life.reception.review(w['id'], critic, life.night)
    review.update(text='Лескова пишет сказ, но голос рассказчика у неё ещё учится у Тиховой.', words_pending=False,
                  about='«Ключи»')
    return life, writer, composer, w, critic, review


class AliasTests(unittest.TestCase):
    def test_names_link_with_case_endings_longest_first_and_never_ambiguously(self):
        ents = {'creator:a': {'type': 'creator', 'aliases': ['Вера Тихова']},
                'creator:b': {'type': 'creator', 'aliases': ['Тихов']},
                'school:skaz': {'type': 'school', 'aliases': ['Сказ']},
                'thing:x': {'type': 'thing', 'aliases': ['Ключ']},
                'thing:y': {'type': 'thing', 'aliases': ['ключ']}}
        index = Index(ents)
        text = 'О Вере Тиховой писали в жанре сказа; Тихову хвалили; ключ потерян; сказка не в счёт.'
        found = [(text[s:e], eid) for s, e, eid in index.link(text)]
        self.assertIn(('Вере Тиховой', 'creator:a'), found)      # the longer name wins over «Тихов»
        self.assertIn(('сказа', 'school:skaz'), found)          # a school in lower case, with its ending
        self.assertIn(('Тихову', 'creator:b'), found)
        self.assertNotIn('сказка', [t for t, _ in found])       # another word, not an ending
        self.assertFalse([e for _, e in found if e.startswith('thing:')])  # «ключ» belongs to two entries
        self.assertEqual(index.link(text), Index(ents).link(text))       # deterministic
        self.assertEqual(Index(ents).link('о вере тиховой'), [])          # persons are written with a capital


class LexiconTests(unittest.TestCase):
    def setUp(self):
        Pen.calls = []

    def test_entries_cite_their_primary_sources_by_id(self):
        life, writer, composer, w, critic, review = atelier()
        with tempfile.TemporaryDirectory() as tmp:
            report = lexicon.update(life, tmp, writer_factory=Pen)
            lex = json.loads((Path(tmp)/'lexicon.json').read_text())
        entries = lex['entries']
        for eid in (f'creator:{writer.id}', f'creator:{composer.id}', f'work:{w["id"]}', 'school:skaz',
                    f'critic:{critic["id"]}', lexicon.thing_id('place', 'Слобода')):
            self.assertIn(eid, entries)
            self.assertEqual(entries[eid]['edition'], 1)
            for p in entries[eid]['paragraphs']:
                self.assertTrue(p['sources'])
                self.assertTrue(set(p['sources']) <= set(lex['sources']))
                self.assertNotIn('[work:nowhere]', p['text'])
                self.assertIn(f'[{p["sources"][0]}]', p['text'])
        work = entries[f'work:{w["id"]}']
        self.assertEqual({p['topic'] for p in work['paragraphs']}, {'work', 'reception'})
        self.assertEqual(next(p for p in work['paragraphs'] if p['topic'] == 'reception')['sources'],
                         [f'review:{review["id"]}'])
        rels = {(r['type'], r['from'], r['to']) for r in lex['entries'][f'work:{w["id"]}']['relations']}
        self.assertIn(('author_of', f'creator:{writer.id}', f'work:{w["id"]}'), rels)
        self.assertIn(('in_school', f'work:{w["id"]}', 'school:skaz'), rels)
        self.assertIn(('reviewed', f'critic:{critic["id"]}', f'work:{w["id"]}'), rels)
        self.assertIn(('appears_in', lexicon.thing_id('place', 'Слобода'), f'work:{w["id"]}'), rels)
        critic_rels = {(r['type'], r['to'], r.get('source')) for r in entries[f'critic:{critic["id"]}']['relations']}
        # The review names the composer and the school: deterministic mentions, no model asked.
        self.assertIn(('mentions', f'creator:{composer.id}', f'review:{review["id"]}'), critic_rels)
        self.assertIn(('mentions', 'school:skaz', f'review:{review["id"]}'), critic_rels)
        self.assertIn(('student_of', f'creator:{writer.id}', f'creator:{composer.id}'),
                      {(r['type'], r['from'], r['to']) for r in entries[f'creator:{writer.id}']['relations']})
        self.assertFalse(report['errors'])

    def test_only_stale_paragraphs_are_rewritten_and_old_editions_stay(self):
        life, writer, composer, w, critic, review = atelier()
        with tempfile.TemporaryDirectory() as tmp:
            lexicon.update(life, tmp, writer_factory=Pen)
            first = lexicon.load(tmp)['entries'][f'work:{w["id"]}']
            calls = len(Pen.calls)
            again = lexicon.update(life, tmp, writer_factory=Pen)
            self.assertEqual((again['calls'], again['revised']), (0, []))
            self.assertEqual(len(Pen.calls), calls)
            review['text'] = 'Перечитал «Ключи»: сказ держится, Лескова нашла свой голос.'
            third = lexicon.update(life, tmp, writer_factory=Pen)
            entries = lexicon.load(tmp)['entries']
        # The review is a source of three paragraphs: the work's reception, the critic's writings, the author's.
        self.assertEqual(sorted(third['revised']), sorted([f'work:{w["id"]}', f'critic:{critic["id"]}',
                                                           f'creator:{writer.id}']))
        self.assertEqual(sorted(Pen.calls[calls:]), sorted([f'lexicon:work:{w["id"]}:reception',
                                                           f'lexicon:critic:{critic["id"]}:writings',
                                                           f'lexicon:creator:{writer.id}:reception']))
        work = entries[f'work:{w["id"]}']
        self.assertEqual(work['edition'], 2)
        self.assertEqual(work['editions'][0]['edition'], 1)
        self.assertEqual(work['editions'][0]['paragraphs'], first['paragraphs'])   # the old edition is kept whole
        now = {p['topic']: p for p in work['paragraphs']}
        was = {p['topic']: p for p in first['paragraphs']}
        self.assertEqual(now['work'], was['work'])                                 # its sources did not change
        self.assertNotEqual(now['reception']['text'], was['reception']['text'])
        self.assertEqual(now['reception']['edition'], 2)
        self.assertEqual(entries['school:skaz']['edition'], 1)

    def test_a_small_budget_catches_up_over_several_calls(self):
        life, *_ = atelier()
        with tempfile.TemporaryDirectory() as tmp:
            first = lexicon.update(life, tmp, writer_factory=Pen, limit=3)
            self.assertLessEqual(first['calls'], 3)
            self.assertGreater(first['pending'], 0)
            for _ in range(40):
                if not lexicon.update(life, tmp, writer_factory=Pen, limit=3)['pending']:
                    break
            self.assertEqual(lexicon.update(life, tmp, writer_factory=Pen, limit=3)['calls'], 0)

    def test_the_gallery_shows_the_index_and_linked_entries(self):
        life, writer, composer, w, critic, review = atelier()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root/'lineage.json').write_text(json.dumps(life.state()))
            lexicon.update(life, root, writer_factory=Pen)
            review['text'] = 'Второе чтение: сказ стал увереннее.'
            lexicon.update(life, root, writer_factory=Pen)
            # The Lexicon is written in Russian: it lives under ru/.
            out = site(Atelier(root), root/'site')/'ru'
            index = (out/'lexicon.html').read_text()
            page = (out/lex_page(f'work:{w["id"]}')).read_text()
            self.assertIn(f'href="{lex_page(f"creator:{writer.id}")}"', index)
            self.assertIn('Ключи', index)
            # Names in the prose link to their entries; citations link to the primary sources.
            self.assertIn(f'<a href="{lex_page(f"creator:{composer.id}")}">Вере Тиховой</a>', page)
            self.assertIn(f'<a href="{lex_page("school:skaz")}">сказе</a>', page)
            self.assertIn(f'href="work-{w["id"]}.html"', page)
            self.assertIn(f'href="critic-{critic["id"]}.html"', page)
            self.assertIn('Прежние издания', page)
            self.assertIn('издание 1', page)
            self.assertIn('href="lexicon.html"', (out/'index.html').read_text())


if __name__ == '__main__':
    unittest.main()
