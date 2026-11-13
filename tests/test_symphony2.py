import unittest

from mnemosyne.music import symphony2 as g


class SymphonyV2Tests(unittest.TestCase):
    def test_example_is_valid_and_lasts_a_symphony(self):
        self.assertTrue(1200 <= g.validate(g.example()) <= 2700)

    def test_unknown_fields_are_refused_not_ignored(self):
        plan = g.example()
        plan['movements'][0]['sections'][0]['layers'][0]['silent'] = ['harp']
        with self.assertRaisesRegex(ValueError, 'not realized by grammar v2'):
            g.validate(plan)
        plan = g.example()
        plan['movements'][0]['sections'][0]['notes'] = 'free text is kept, not realized'
        g.validate(plan)

    def test_only_named_instruments_sound_and_meters_change(self):
        plan = g.example()
        score, op, assignment, dev = g.movement(plan, 0)
        opening, growth = dev['sections'][0], dev['sections'][1]
        self.assertEqual(set(opening['sounding']), {'clarinet', 'cello_section', 'viola_section', 'violin_2_section'})
        self.assertIn('harp', opening['tacet'])
        self.assertIn('timpani', opening['tacet'])
        self.assertEqual((opening['meter'], growth['meter']), ('3/4', '2/4'))
        self.assertEqual(op['meters'][1], (opening['bars'] * 3, '2/4'))
        played = {p['instrument'] for p in assignment['players'] if p['events']}
        named = {n for s in plan['movements'][0]['sections'] for l in s['layers'] for n in l['instruments']}
        self.assertEqual(played, named)
        harp = [e for p in assignment['players'] if p['instrument'] == 'harp' for e in p['events']]
        self.assertTrue(all(e['at'] >= dev['sections'][4]['start_quarters'] for e in harp))
        signatures = {ts.ratioString for ts in score.parts[0].recurse().getElementsByClass('TimeSignature')}
        self.assertEqual(signatures, {'3/4', '2/4'})

    def test_waltz_bass_on_the_downbeat_only(self):
        plan = g.example()
        _, _, assignment, dev = g.movement(plan, 0)
        cello = [e for p in assignment['players'] if p['instrument'] == 'cello_section' for e in p['events']
                 if e['at'] < dev['sections'][0]['end_quarters']]
        self.assertTrue(cello and all(e['at'] % 3 == 0 for e in cello))
        self.assertTrue(all(e['technique'] == 'pizzicato' for e in cello))

    def test_general_pause_is_silent(self):
        _, _, assignment, dev = g.movement(g.example(), 1)
        pause = dev['sections'][2]
        self.assertEqual(pause['sounding'], {})
        inside = [e for p in assignment['players'] for e in p['events']
                  if pause['start_quarters'] <= e['at'] < pause['end_quarters']]
        self.assertEqual(inside, [])

    def test_plan_changes_change_notes(self):
        a = g.example()
        b = g.example()
        b['movements'][0]['sections'][0]['progression'] = [1, 6, 2, 5]
        b['movements'][0]['sections'][0]['mode'] = 'minor'
        notes = lambda plan: [(e['at'], e['pitches']) for p in g.movement(plan, 0)[2]['players'] for e in p['events']]
        self.assertNotEqual(notes(a), notes(b))

    def test_dynamic_ramp(self):
        _, _, assignment, dev = g.movement(g.example(), 0)
        sec = dev['sections'][2]
        v = [e['velocity'] for p in assignment['players'] if p['instrument'] == 'violin_1_section'
             for e in sorted(p['events'], key=lambda e: e['at']) if sec['start_quarters'] <= e['at'] < sec['end_quarters']]
        self.assertLess(v[0], v[-1])

    def test_a_single_held_tone_is_a_theme(self):
        plan = g.example()
        plan['themes']['support'] = {'pitches': [50], 'durations': [4], 'source': {'kind': 'composed'}}
        plan['movements'][1]['sections'][0]['layers'].append(
            {'instruments': ['bassoon'], 'role': 'drone', 'material': 'theme:support', 'dynamic': 'pp'})
        g.validate(plan)
        g.movement(plan, 1)
        plan['themes']['support']['durations'] = [1.414]
        with self.assertRaisesRegex(ValueError, 'time_scale'):
            g.validate(plan)

    def test_tempo_canon_voice_keeps_its_ratio(self):
        plan = g.example()
        sec = plan['movements'][1]['sections'][0]
        sec['layers'].append({'instruments': ['oboe'], 'role': 'counter', 'material': 'theme:waltz', 'time_scale': 1.414})
        g.validate(plan)
        _, _, assignment, dev = g.movement(plan, 1)
        end = dev['sections'][0]['end_quarters']
        oboe = sorted(e['at'] for p in assignment['players'] if p['instrument'] == 'oboe' for e in p['events'] if e['at'] < end)
        cello = sorted(e['at'] for p in assignment['players'] if p['instrument'] == 'cello_section' for e in p['events'] if e['at'] < end)
        self.assertLess(len(oboe), len(cello))


if __name__ == '__main__':
    unittest.main()
