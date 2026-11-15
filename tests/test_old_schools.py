"""Older traditions as schools: each composes deterministically and uses its signature device."""
import json
from pathlib import Path
import statistics
import unittest

from test_music_schools import fingerprint, PLANS
from mnemosyne.music.schools import SCHOOLS
from mnemosyne.music.schools.common import ENSEMBLES, analyze
from mnemosyne.music.schools.chant import WHITE
from mnemosyne.music.schools.performance import sounding_events
from mnemosyne.music.schools.tonal import MAJOR, HARMONIC_MINOR, chord, roles

OLD = ('ancient_greek', 'gregorian', 'organum', 'ars_nova', 'renaissance_polyphony',
       'fugue', 'basso_continuo', 'classical', 'romantic')


def compose(name, seed=None):
    plan = json.loads((PLANS/f'{name}.json').read_text())
    return SCHOOLS[name].compose(plan, plan['seed'] if seed is None else seed), plan


def events(part):
    return [(at, length, pitches) for at, length, pitches, *_ in sounding_events(part)]


class OldSchoolTests(unittest.TestCase):
    def test_registered_deterministic_and_in_range(self):
        for name in OLD:
            with self.subTest(school=name):
                self.assertIn(name, SCHOOLS)
                a, plan = compose(name)
                b, _ = compose(name)
                self.assertEqual(fingerprint(a), fingerprint(b))
                info = analyze(a, plan)
                self.assertEqual(info['empty_parts'], 0)
                rules = SCHOOLS[name].FREE_CHANNELS
                self.assertEqual((rules['period_quarters'], rules['levels'], rules['step_percent'],
                                  rules['max_deviation_percent']), (.5, 16, .25, 1.875))
                self.assertTrue(rules['dynamics'])

    def test_gregorian_moves_by_step_inside_one_mode(self):
        score, plan = compose('gregorian')
        mode = score.editorial.mode
        chant = [p for _, _, ps in events(score.parts[0]) for p in ps]
        self.assertTrue(all(int(p) % 12 in WHITE for part in score.parts for _, _, ps in events(part) for p in ps))
        steps = [abs(b-a) for a, b in zip(chant, chant[1:])]
        self.assertGreater(sum(s <= 2 for s in steps)/len(steps), .75)
        self.assertLessEqual(max(chant)-min(chant), 16)  # an ambitus, not a free range
        ison = {int(p) % 12 for _, _, ps in events(score.parts[-1]) for p in ps}
        self.assertEqual(ison, {mode['final']})

    def test_ancient_greek_enharmonic_quarter_tones_and_feet(self):
        score, plan = compose('ancient_greek')
        song = events(score.parts[0])
        self.assertTrue(any(p % 1 == .5 for _, _, ps in song for p in ps))
        self.assertTrue({length for _, length, _ in song} <= {.5, 1, 1.5})

    def test_organum_tenor_holds_while_upper_voices_move_in_concords(self):
        score, plan = compose('organum')
        tenors = score.editorial.tenor_parts
        tenor = events(score.parts[tenors[0]])
        uppers = [i for i in range(len(score.parts)) if i not in tenors]
        upper_lengths = [l for i in uppers for _, l, _ in events(score.parts[i])]
        self.assertGreater(statistics.mean(l for _, l, _ in tenor), 3*statistics.mean(upper_lengths))
        onsets = {at: ps[0] for at, _, ps in tenor}
        checked = 0
        for i in uppers:
            for at, _, ps in events(score.parts[i]):
                if at in onsets:
                    self.assertIn((ps[0]-onsets[at]) % 12, (0, 7))
                    checked += 1
        self.assertGreater(checked, 10)

    def test_ars_nova_talea_and_color_repeat_with_different_periods(self):
        score, plan = compose('ars_nova')
        talea, color = score.editorial.talea, score.editorial.color
        notes = [v for v, rest in talea if not rest]
        self.assertNotEqual(len(color) % len(notes), 0)
        tenor = events(score.parts[score.editorial.tenor_parts[0]])
        first_section_end = plan['form'][0]['duration']*plan['tempo']/60 - 3
        body = [(at, l, ps[0]) for at, l, ps in tenor if at < first_section_end]
        onsets, at = [], 0
        while len(onsets) < len(body):
            for value, rest in talea:
                if not rest:
                    onsets.append(at)
                at += value
        self.assertEqual([a for a, _, _ in body], onsets[:len(body)])
        pitches = [p for _, _, p in body]
        period = len(color)
        self.assertGreater(len(pitches), period)
        self.assertEqual(pitches[period:], pitches[:len(pitches)-period])
        # Double leading-tone cadence: the highest upper voice rises a semitone at the end.
        top = [i for i in range(len(score.parts)) if i not in score.editorial.tenor_parts][0]
        ending = events(score.parts[top])[-2:]
        self.assertEqual(ending[1][2][0]-ending[0][2][0], 1)

    def test_renaissance_points_of_imitation_enter_at_fixed_distances(self):
        score, plan = compose('renaissance_polyphony')
        lines = score.editorial.lines
        self.assertTrue(score.editorial.points)
        for point in score.editorial.points:
            times = [at for at, _, _ in point['entries']]
            self.assertEqual([b-a for a, b in zip(times, times[1:])], [point['gap']]*(len(times)-1))
            rhythm = [v for _, v in point['subject']]
            for at, line, _ in point['entries']:
                part = events(score.parts[lines[line][0]])
                start = next(k for k, e in enumerate(part) if e[0] == at)
                got = [l for _, l, _ in part[start:start+len(rhythm)]]
                self.assertEqual(got[:-1], rhythm[:-1])  # the last head note may run on

    def test_renaissance_has_no_parallel_fifths_or_octaves(self):
        from mnemosyne.music.schools.renaissance_polyphony import parallel, parallels
        self.assertTrue(parallel(60, 62, 53, 55))      # fifths moving up together
        self.assertTrue(parallel(60, 59, 48, 47))      # octaves moving down together
        self.assertFalse(parallel(60, 62, 53, 52))     # contrary motion
        self.assertFalse(parallel(60, 60, 53, 55))     # oblique motion
        score, plan = compose('renaissance_polyphony')
        lines = score.editorial.lines
        n = len(lines)
        for line_events, finals in zip(score.editorial.line_events, score.editorial.line_finals):
            self.assertEqual(parallels(line_events, finals, n), [])

        def sounding(part_events, t):
            return next((ps[0] for a, l, ps in part_events if a <= t < a+l), None)

        line_of = {i: k for k, group in enumerate(lines) for i in group}
        checked = 0
        for x in range(len(score.parts)):
            for y in range(x+1, len(score.parts)):
                if line_of[x] == line_of[y]:
                    continue  # doublings of one line in octaves are not two voices
                ex, ey = events(score.parts[x]), events(score.parts[y])
                times = sorted({a for a, _, _ in ex+ey} | {a+l for a, l, _ in ex+ey})
                verticals = [(t, sounding(ex, t), sounding(ey, t)) for t in times]
                for (_, x0, y0), (t, x1, y1) in zip(verticals, verticals[1:]):
                    self.assertFalse(parallel(x0, x1, y0, y1), (t, x, y))
                    checked += 1
        self.assertGreater(checked, 100)

    def test_fugue_answers_at_the_fifth_and_overlaps_in_stretto(self):
        score, plan = compose('fugue')
        subject, answer = score.editorial.subject, score.editorial.answer
        tonic = int(plan.get('tonic', 60)) % 12
        for k, ((_, _, s), (_, _, a)) in enumerate(zip(subject, answer)):
            expected = 5 if k == 0 and (s-tonic) % 12 == 7 else 7
            self.assertEqual(a-s, expected)
        answers = [e for e in score.editorial.entries if e['kind'] == 'answer']
        self.assertTrue(answers)
        for entry in answers:
            self.assertEqual([p % 12 for p in entry['pitches']], [p % 12 for _, _, p in answer][:len(entry['pitches'])])
        stretto = sorted((e for e in score.editorial.entries if e['kind'] == 'stretto'), key=lambda e: e['at'])
        self.assertGreaterEqual(len(stretto), 2)
        self.assertTrue(any(b['at'] < a['end'] for a, b in zip(stretto, stretto[1:])))
        self.assertTrue(any(e['kind'] == 'pedal' for e in score.editorial.entries))

    def test_basso_continuo_bass_every_beat_chords_and_fifth_sequences(self):
        score, plan = compose('basso_continuo')
        names = ENSEMBLES[plan['ensemble']]
        role = roles(names)
        bass = next(i for i, r in role.items() if r == 'bass')
        units = score.editorial.units
        body = units[-1][0]+16
        onsets = {at for at, _, _ in events(score.parts[bass])}
        self.assertTrue(all(beat in onsets for beat in range(int(body))))
        keys = next(i for i, n in enumerate(names) if n == 'piano')
        self.assertTrue(all(len(ps) >= 3 for at, _, ps in events(score.parts[keys]) if at < body))
        tonic = int(plan.get('tonic', 60)) % 12
        episodes = [s for s in score.editorial.slots if s[3] == 'episode']
        self.assertTrue(episodes)
        bass_at = {at: ps[0] for at, _, ps in events(score.parts[bass])}
        for start, kind, _ in units:
            if kind != 'episode':
                continue
            chain = [s for s in episodes if start <= s[0] < start+12]
            roots = [chord(tonic, numeral, key)[0] for _, numeral, key, _ in chain]
            # Diatonic circle of fifths: every link a fifth down, one of them diminished.
            links = [(b-a) % 12 for a, b in zip(roots, roots[1:])]
            self.assertEqual(len(links), 5)
            self.assertTrue(set(links) <= {5, 6} and links.count(6) <= 1, links)
            self.assertEqual([int(bass_at[at]) % 12 for at, *_ in chain], roots)
        levels = {d.value for d in score.recurse().getElementsByClass('Dynamic')}
        self.assertEqual(levels, {'f', 'p'})

    def test_classical_phrases_cadence_on_tonic_or_dominant(self):
        score, plan = compose('classical')
        tonic = int(plan.get('tonic', 60)) % 12
        names = ENSEMBLES[plan['ensemble']]
        bass = next(i for i, r in roles(names).items() if r == 'bass')
        bass_at = {at: ps[0] for at, _, ps in events(score.parts[bass])}
        expected = {'half': 'V', 'full': 'I', 'modulating': 'I', 'retransition': 'V7'}
        cadences = score.editorial.cadences
        self.assertGreater(len(cadences), 6)
        for start, (numeral, key), kind in cadences:
            self.assertEqual(numeral, expected[kind])
            self.assertEqual(int(bass_at[start+14]) % 12, chord(tonic, numeral, key)[0])
        self.assertEqual({key for _, (_, key), _ in cadences}, {0, 7})  # there and back

    def test_classical_minor_cadences_on_i_or_v_with_raised_leading_tone(self):
        plan = json.loads((PLANS/'classical.json').read_text())
        plan['mode'] = 'minor'
        plan['tonic'] = 57
        from mnemosyne.music.schools.plan import SchoolPlan
        SchoolPlan.model_validate(plan)
        score = SCHOOLS['classical'].compose(plan, plan['seed'])
        self.assertEqual(score.editorial.mode, 'minor')
        tonic = 57 % 12
        names = ENSEMBLES[plan['ensemble']]
        bass = next(i for i, r in roles(names).items() if r == 'bass')
        bass_at = {at: ps[0] for at, _, ps in events(score.parts[bass])}
        expected = {'half': 'V', 'full': {0: 'i', 3: 'I'}, 'modulating': {3: 'I'}, 'retransition': 'V7'}
        cadences = score.editorial.cadences
        self.assertGreater(len(cadences), 6)
        for start, (numeral, key), kind in cadences:
            want = expected[kind]
            self.assertEqual(numeral, want[key] if isinstance(want, dict) else want)
            self.assertEqual(int(bass_at[start+14]) % 12, chord(tonic, numeral, key)[0])
        self.assertEqual({key for _, (_, key), _ in cadences}, {0, 3})  # to the relative major and back
        pcs = {int(p) % 12 for part in score.parts for _, _, ps in events(part) for p in ps}
        self.assertIn((tonic+11) % 12, pcs)  # G sharp: the raised leading tone of A minor
        self.assertIn((tonic+3) % 12, pcs)   # C: the minor third / the relative major
        home_end = min(start for start, _, kind in cadences if kind == 'modulating')
        home = {int(p) % 12 for part in score.parts for at, _, ps in events(part) for p in ps if at < home_end}
        self.assertIn((tonic+11) % 12, home)
        self.assertNotIn((tonic+10) % 12, home)  # harmonic minor: no natural seventh at home
        default, _ = compose('classical')
        self.assertEqual(default.editorial.mode, 'major')

    def test_romantic_chromatic_harmony_and_climax_register(self):
        score, plan = compose('romantic')
        tonic = int(plan.get('tonic', 60)) % 12
        home = {(tonic+x) % 12 for x in (HARMONIC_MINOR if score.editorial.minor else MAJOR)}
        pcs = [int(p) % 12 for part in score.parts for _, _, ps in events(part) for p in ps]
        self.assertGreater(sum(pc not in home for pc in pcs)/len(pcs), .05)
        melody = events(score.parts[0])
        total = plan['duration']*plan['tempo']/60
        first = max(ps[0] for at, _, ps in melody if at < total/4)
        climax = max(ps[0] for at, _, ps in melody if .5*total <= at < .75*total)
        self.assertGreater(climax, first)

    def test_dynamics_channel_carries_and_decodes_without_changing_notes(self):
        import tempfile
        from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey
        from music21 import converter
        from mnemosyne.music.render import note_events
        from mnemosyne.state.collect import archive
        from mnemosyne.weave import fountain, payload, registry, schools, school_series, surface
        from mnemosyne.weave.school_audit import plan_for
        key = X25519PrivateKey.generate()
        data = archive([{'apiVersion': 'v1', 'kind': 'Namespace', 'metadata': {'name': 'leonia'}}])
        encoder = fountain.Encoder(payload.seal(data, key.public_key(), context=fountain.DOMAIN), 120, key)
        with tempfile.TemporaryDirectory() as directory:
            for name in OLD:
                with self.subTest(school=name):
                    plan = plan_for(name)
                    score = SCHOOLS[name].compose(plan, plan['seed'])
                    path = Path(directory)/f'{name}.musicxml'
                    score.write('musicxml', fp=path)
                    root = schools.prepare(surface.read(path), name)
                    self.assertGreaterEqual(schools.capacity(root), 32)
                    root = registry.mark(root, (name, 'dynamics-fountain', '2'))
                    frames = [encoder.frame(encoder.k)]
                    woven = Path(directory)/f'{name}.woven.musicxml'
                    surface.write(school_series.encode_many(root, frames, key), woven)
                    self.assertEqual(registry.decode(woven, key).frame, frames)
                    parsed = converter.parse(woven).toSoundingPitch()
                    self.assertEqual(note_events(parsed.stripTies()), note_events(score.stripTies()))

    def test_orchestrated_plans_validate_and_orchestrate(self):
        from mnemosyne.music.orchestration import orchestrate, school_lines
        from mnemosyne.music.schools.plan import SchoolPlan
        folder = Path(SCHOOLS['classical'].__file__).parent/'orchestrated_plans'
        for name in OLD:
            with self.subTest(school=name):
                plan = json.loads((folder/f'{name}.json').read_text())
                SchoolPlan.model_validate(plan)
                self.assertEqual((plan['school'], plan['audio_profile']), (name, 'native_sfz'))
                score = SCHOOLS[name].compose(plan, plan['seed'])
                _, assignment = orchestrate(school_lines(score, plan), plan)
                self.assertTrue(any(p['events'] for p in assignment['players']))

    def test_every_new_school_has_poetics(self):
        from mnemosyne.writing import poetics
        for name in OLD:
            with self.subTest(school=name):
                p = poetics.load(name)
                self.assertEqual(p['id'], name)
                self.assertEqual(p['form']['code'], f'src/mnemosyne/music/schools/{name}.py')
                self.assertIn('Слушатель', poetics.full(name))


if __name__ == '__main__':
    unittest.main()
