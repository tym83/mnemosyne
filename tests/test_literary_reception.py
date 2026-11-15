"""Critics read a literary work as text: its words, its school's poetics, its language and translation."""
import unittest
from datetime import datetime

from mnemosyne.lineage import Lineage
from mnemosyne.reception import LITERARY, ReviewWords, arts_of

TALE = 'Ну, значит, пришёл к нам в слободу один человек, и стал он, братцы, ключи ковать без замков.'


def life_with(art, **work):
    life = Lineage('leonia', datetime(2025, 1, 1), seed=2)
    a = next(a for a in life.artists if a.art == art)
    a.name = 'Анна Лескова' if art == 'literature' else 'Otto Klang'
    w = life._work(a, observation=dict(feature=[.5] * 4, novelty=1, quality=.8, verdict='accept'))
    w.update(work)
    life.reception.register(a, w)
    critic = next(c for c in life.reception.critics if a.art in arts_of(c))
    life.reception.review(w['id'], critic, life.night)
    return life, a, w


class Recorder:
    calls = []

    def __init__(self, nb):
        pass

    def ask(self, system, prompt, schema, step):
        Recorder.calls.append((system, prompt))
        return ReviewWords(text='Рецензия.', score=.6)


class LiteraryReceptionTests(unittest.TestCase):
    def setUp(self):
        Recorder.calls = []

    def test_a_literary_review_reads_the_text_and_the_school_poetics(self):
        life, a, w = life_with('literature', school='skaz', title='Ключи', text=TALE, language='pt',
                               translation='Перевод сказа.', idea='Замысел о ключах')
        a.language = 'pt'
        life.reception.write_words(Recorder, life=life)
        system, prompt = Recorder.calls[-1]
        self.assertIn(TALE, prompt)
        self.assertIn('Перевод сказа.', prompt)
        self.assertIn('Школа «Сказ»', prompt)          # the poetics as words
        self.assertIn('Манифест:', prompt)
        self.assertIn('Жанры школы:', prompt)
        self.assertIn('Язык оригинала: Portuguese', prompt)
        self.assertIn(LITERARY, system)
        review = next(r for r in life.reception.reviews if r['work'] == w['id'])
        self.assertEqual(review['text'], 'Рецензия.')
        self.assertEqual(review['about'], '«Ключи»')

    def test_a_music_review_keeps_its_own_path(self):
        life, a, w = life_with('music', school='tintinnabuli', concept='Форма из колоколов')
        life.reception.write_words(Recorder, life=life)
        system, prompt = Recorder.calls[-1]
        self.assertNotIn(LITERARY, system)
        self.assertIn('Искусство: музыка', prompt)
        self.assertIn('Замысел формы: Форма из колоколов', prompt)

    def test_an_essay_beside_reviews_does_not_stop_the_critics(self):
        life, a, w = life_with('literature', school='haiku', text='Старый пруд.')
        life.reception.essay('creator', a.id, a.id, life.reception.critics[0], life.night)
        life.reception.write_words(Recorder, life=life)
        self.assertTrue(all(not r['words_pending'] for r in life.reception.reviews))


if __name__ == '__main__':
    unittest.main()
