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

    def test_written_pitches_once_at_the_offset_and_held_material(self):
        plan = g.example()
        plan['themes']['support'] = {'pitches': [50], 'durations': [4], 'source': {'kind': 'composed'}}
        sec = plan['movements'][1]['sections'][0]
        sec['layers'] = [
            {'instruments': ['oboe'], 'role': 'melody', 'material': 'theme:waltz', 'offset': 3, 'bars': [2, 24]},
            {'instruments': ['cello_section'], 'role': 'drone', 'material': 'theme:support', 'pattern': 'sustain',
             'register': [50, 50], 'bars': [3, 5]}]
        _, _, assignment, dev = g.movement(plan, 1)
        end = dev['sections'][0]['end_quarters']
        oboe = sorted((e['at'], e['pitches'][0]) for p in assignment['players'] if p['instrument'] == 'oboe'
                      for e in p['events'] if e['at'] < end)
        self.assertEqual(oboe[0][0], 4 + 3)
        self.assertEqual([p for _, p in oboe][:6], plan['themes']['waltz']['pitches'])
        self.assertEqual(len(oboe), len(plan['themes']['waltz']['pitches']))  # stated once, then silent
        cello = [e for p in assignment['players'] if p['instrument'] == 'cello_section' for e in p['events']]
        self.assertEqual({e['pitches'][0] for e in cello}, {50})
        self.assertEqual(min(e['at'] for e in cello), 8)

    def test_pitched_percussion_plays_in_a_percussion_layer(self):
        plan = g.example()
        plan['orchestra'].append({'instrument': 'tubular_bells', 'count': 1})
        plan['movements'][0]['sections'][3]['layers'].append(
            {'instruments': ['tubular_bells'], 'role': 'percussion', 'pattern': 'hits', 'density': .5})
        g.validate(plan)
        _, _, assignment, _ = g.movement(plan, 0)
        self.assertTrue(any(p['events'] for p in assignment['players'] if p['instrument'] == 'tubular_bells'))
        self.assertEqual(g.playable('glockenspiel'), (79, 84))

    def test_fixed_pitch_instruments_play_no_quarter_tones(self):
        self.assertEqual(g.place(60.5, 'piano') % 1, 0)
        self.assertEqual(g.place(60.5, 'harp') % 1, 0)
        self.assertEqual(g.place(60.5, 'violin_1_section'), 60.5)

    def test_a_written_pitch_without_a_sample_moves_to_an_octave_that_sounds(self):
        # Timpani range reaches 60, the samples only 48: a register [36, 53] cannot keep 53.
        self.assertEqual(g.place(53, 'timpani', register=(36, 53)), 41)
        self.assertEqual(g.place(45, 'timpani', register=(36, 53)), 45)

    def test_a_studio_plan_with_a_timpani_chord_is_realized(self):
        # A plan from the cluster: a two-note timpani chord adds a player, and its notes reach past the samples.
        import json
        from pathlib import Path
        from mnemosyne.music.composer import Method, validate_plan
        data = json.loads((Path(__file__).parent/'fixtures'/'sketch_timpani_chord.json').read_text())
        validate_plan(data['plan'], Method(**data['method']), sketch=True)

    def test_a_wide_chord_is_played_by_more_players_of_the_same_instrument(self):
        plan = g.example()
        sec = plan['movements'][1]['sections'][2]          # the general pause: nothing else sounds there
        sec['layers'] = [{'instruments': ['horn'], 'role': 'pad', 'pattern': 'sustain',
                          'material': 'harmony', 'dynamic': 'p'}]
        from unittest.mock import patch
        wide = [50, 53, 57, 60, 62, 65, 69]                 # seven tones for four horns
        with patch.object(g, 'chord', return_value=wide):
            _, op, assignment, dev = g.movement(plan, 1)
        pause = dev['sections'][2]
        sounding = {p['instrument'] for p in assignment['players'] for e in p['events']
                    if pause['start_quarters'] <= e['at'] < pause['end_quarters']}
        desks = {p['id'] for p in assignment['players'] for e in p['events']
                 if pause['start_quarters'] <= e['at'] < pause['end_quarters']}
        self.assertEqual(sounding, {'horn'})                # the composer's timbre, nobody else
        self.assertEqual(len(desks), 7)
        self.assertEqual(dev['added_players']['horn'], 3)
        self.assertEqual(next(e for e in op['ensemble'] if e['instrument'] == 'horn')['count'], 7)

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


    def test_section_tempo_marks_seconds_and_total(self):
        from mnemosyne.music import tempo_map
        plan = g.example()
        before = g.validate(plan)
        old = g.movement(plan, 1)[3]
        mv = plan['movements'][1]  # tempo 50: A 24×4/4, B 20×5/4, C 8×4/4, B 20×5/4, A 24×4/4
        mv['sections'][1]['tempo'] = 75
        score, op, assignment, dev = g.movement(plan, 1)
        b = dev['sections'][1]
        self.assertEqual(b['tempo'], 75)
        self.assertAlmostEqual(b['duration_seconds'], 100 * 60 / 75)
        self.assertAlmostEqual(dev['sections'][2]['start_seconds'], 96 * 60 / 50 + 100 * 60 / 75)
        self.assertAlmostEqual(dev['seconds'], old['seconds'] - 100 * 60 / 50 + 100 * 60 / 75)
        self.assertAlmostEqual(op['duration'], dev['seconds'])
        self.assertAlmostEqual(g.validate(plan, study=True), before - 100 * 60 / 50 + 100 * 60 / 75)
        self.assertEqual(op['tempo_map'], [[0, 50.0, True], [96, 75.0, True], [196, 50.0, True]])
        self.assertEqual(op['quarters'], 424)
        self.assertEqual(tempo_map.total_quarters(op), 424)
        part = score.parts[0]
        marks = [(float(m.getOffsetInHierarchy(part)), m.number)
                 for m in part.recurse().getElementsByClass('MetronomeMark')]
        self.assertEqual(marks, [(0.0, 50), (96.0, 75), (196.0, 50)])
        # The score's own timing (music21 reads the marks) agrees with the report.
        self.assertAlmostEqual(sum((e - a) * 60 / m.number for a, e, m in score.metronomeMarkBoundaries()),
                               dev['seconds'])
        # Notes stay where they were in quarters: only the performance clock changed.
        self.assertEqual([(p['id'], [e['at'] for e in p['events']]) for p in assignment['players']],
                         [(p['id'], [e['at'] for e in p['events']]) for p in g.movement(g.example(), 1)[2]['players']])

    def test_gradual_tempo_change_steps_each_quarter(self):
        from mnemosyne.music import tempo_map
        plan = g.example()
        sec = plan['movements'][0]['sections'][4]  # dissolution: 24 bars of 3/4 at 66
        sec['tempo_to'] = 44
        g.validate(plan)
        score, op, _, dev = g.movement(plan, 0)
        last = dev['sections'][4]
        self.assertEqual(last['tempo_to'], 44)
        steps = [x for x in op['tempo_map'] if x[0] >= last['start_quarters']]
        self.assertEqual(len(steps), 71)  # quarters 1..71 change; quarter 0 keeps the movement tempo
        self.assertEqual(steps[-1], [last['end_quarters'] - 1, 44.0, True])
        expected = sum(60 / (66 + (44 - 66) * k / 71) for k in range(72))
        self.assertAlmostEqual(last['duration_seconds'], expected)
        self.assertAlmostEqual(tempo_map.section_seconds(72, 66, 44), expected)
        self.assertAlmostEqual(op['duration'], dev['seconds'])
        self.assertAlmostEqual(sum((e - a) * 60 / m.number for a, e, m in score.metronomeMarkBoundaries()),
                               dev['seconds'])
        self.assertIn([last['start_quarters'], 'rit.'], op['tempo_text'])
        words = [t.content for t in score.parts[0].recurse().getElementsByClass('TextExpression')]
        self.assertIn('rit.', words)
        shown = [m.number for m in score.parts[0].recurse().getElementsByClass('MetronomeMark') if not m.numberImplicit]
        self.assertEqual(shown, [66, 44])
        plan['movements'][0]['sections'][4]['tempo_to'] = 300
        with self.assertRaisesRegex(ValueError, 'tempo_to 30–240'):
            g.validate(plan)

    def test_tempo_map_reaches_the_midi_file(self):
        import tempfile
        from pathlib import Path
        from mnemosyne.music.schools.performance import write_midi
        plan = g.example()
        plan['movements'][1]['sections'][1]['tempo'] = 75
        score, op, _, _ = g.movement(plan, 1)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'m.mid'
            write_midi(score, path, op['tempo'], tempo_map=op['tempo_map'])
            data = path.read_bytes()
        tempi = [int.from_bytes(data[i+3:i+6], 'big') for i in range(len(data)-6) if data[i:i+3] == b'\xff\x51\x03']
        self.assertEqual(tempi, [round(6e7/50), round(6e7/75), round(6e7/50)])
        self.assertEqual(tempo_map_seconds(op), op['duration'])

    def test_constant_tempo_movements_are_unchanged(self):
        _, op, _, dev = g.movement(g.example(), 0)
        self.assertNotIn('tempo_map', op)
        self.assertEqual((op['tempo'], op['duration']), (66, dev['seconds']))
        self.assertNotIn('tempo', dev['sections'][0])

    def test_harmony_line_in_thirds_of_a_bar_does_not_read_as_overlap(self):
        # A harmony line steps in bar/3 values: 8.0 + 4/3 is a float, the next onset 28/3 a Fraction.
        plan = g.example()
        plan['movements'][1]['sections'][0]['layers'].append(
            {'instruments': ['bass_trombone'], 'role': 'bass', 'material': 'harmony', 'pattern': 'line', 'repeat': 0})
        g.validate(plan)
        _, _, assignment, _ = g.movement(plan, 1)
        trombone = sorted(e['at'] for p in assignment['players'] if p['instrument'] == 'bass_trombone' for e in p['events'])
        self.assertIn(8 + 4/3, [round(x, 9) for x in trombone] and [8 + 4/3] or [])
        self.assertGreater(len(trombone), 10)


    def test_plain_techniques_and_staccato_without_samples_are_realized(self):
        plan = g.example()
        plan['orchestra'].append({'instrument': 'soprano_choir', 'players': 8})
        sec = plan['movements'][1]['sections'][0]
        sec['layers'] = [
            {'instruments': ['oboe'], 'role': 'melody', 'material': 'theme:waltz', 'technique': 'arco'},
            {'instruments': ['violin_1_section'], 'role': 'pad', 'pattern': 'sustain', 'technique': 'sustain'},
            {'instruments': ['harp'], 'role': 'figuration', 'pattern': 'arpeggio', 'technique': 'staccato'},
            {'instruments': ['soprano_choir'], 'role': 'melody', 'material': 'theme:waltz', 'technique': 'staccato'}]
        g.validate(plan)
        _, _, assignment, dev = g.movement(plan, 1)
        end = dev['sections'][0]['end_quarters']
        tech = lambda name: {e['technique'] for p in assignment['players'] if p['instrument'] == name
                             for e in p['events'] if e['at'] < end}
        self.assertEqual(tech('oboe'), {'sustain'})
        self.assertEqual(tech('violin_1_section'), {'arco'})
        self.assertEqual(tech('harp'), {'sustain'})
        choir = sorted((e['at'], e['duration']) for p in assignment['players'] if p['instrument'] == 'soprano_choir'
                       for e in p['events'])
        # The section augments the theme: its first half note is sung as a quarter, the next enters on time.
        self.assertEqual(choir[:2], [(0.0, 1.0), (2.0, 1.0)])
        for name, tech_name in (('harp', 'pizzicato'), ('flute', 'col_legno')):
            bad = g.example()
            bad['movements'][1]['sections'][0]['layers'][0] = {'instruments': [name], 'role': 'melody',
                                                               'material': 'theme:waltz', 'technique': tech_name}
            with self.assertRaisesRegex(ValueError, f'{tech_name} changes the sound.*available'):
                g.validate(bad)

    def test_unknown_or_mismatched_form_is_free(self):
        plan = g.example()
        plan['movements'][0]['form'] = 'sonata'  # its roles are not the sonata's
        plan['movements'][1]['form'] = 'nocturne with a storm'
        del plan['movements'][2]['form']
        g.validate(plan)
        plan['movements'][0]['sections'][0]['role'] = ''
        with self.assertRaisesRegex(ValueError, 'name every section role'):
            g.validate(plan)

    def test_theme_source_defaults_to_composed(self):
        plan = g.example()
        del plan['themes']['waltz']['source']
        g.validate(plan)
        self.assertEqual(plan['themes']['waltz']['source'], {'kind': 'composed'})

    def test_layers_sharing_an_instrument_never_overlap_on_a_desk(self):
        plan = g.example()
        sec = plan['movements'][1]['sections'][0]  # two oboes in the orchestra
        sec['layers'] = [
            {'instruments': ['oboe'], 'role': 'pad', 'pattern': 'sustain', 'dynamic': 'pp'},
            {'instruments': ['oboe'], 'role': 'melody', 'material': 'theme:waltz', 'repeat': 0},
            {'instruments': ['oboe'], 'role': 'points', 'material': 'row:crowd', 'pattern': 'points', 'density': 1},
            {'instruments': ['oboe'], 'role': 'counter', 'material': 'theme:waltz', 'offset': 1, 'repeat': 0}]
        g.validate(plan)
        _, _, assignment, dev = g.movement(plan, 1)
        for player in assignment['players']:
            events = sorted(player['events'], key=lambda e: e['at'])
            for a, b in zip(events, events[1:]):
                self.assertLessEqual(a['at'] + a['duration'], b['at'] + 1e-9, player['id'])
        adjusted = dev['sections'][0]['adjusted']['oboe']
        self.assertGreater(adjusted.get('truncated', 0) + adjusted.get('dropped', 0), 0)

    def test_more_chord_tones_than_one_harp_holds_keep_the_outer_ones(self):
        from mnemosyne.music.orchestration import Event
        events = [Event(0, 4, tuple(range(60, 81, 2)), 64)]  # eleven tones, one harp of eight
        (chunk,) = g.merge_chords(events, 8, players=1, adjusted=(adjusted := {}), name='harp')
        self.assertEqual(len(chunk[0].pitches), 8)
        self.assertEqual((max(chunk[0].pitches), min(chunk[0].pitches)), (80, 60))
        self.assertEqual(adjusted, {'harp': {'chord_tones_dropped': 3}})
        plan = g.example()
        sec = plan['movements'][1]['sections'][0]
        sec['layers'] = [
            {'instruments': ['harp'], 'role': 'pad', 'material': 'theme:waltz', 'pattern': 'sustain', 'register': [40, 52]},
            {'instruments': ['harp'], 'role': 'pad', 'material': 'theme:waltz', 'pattern': 'sustain', 'register': [64, 76]}]
        g.validate(plan)
        _, _, assignment, dev = g.movement(plan, 1)
        self.assertIn('chord_tones_dropped', dev['sections'][0]['adjusted']['harp'])
        harp = [e for p in assignment['players'] if p['instrument'] == 'harp' for e in p['events']]
        self.assertTrue(harp and all(len(e['pitches']) <= 8 for e in harp))

    def test_an_oversized_plan_is_refused_with_a_way_to_shorten_it(self):
        plan = g.example()
        plan['notes'] = 'x' * g.PLAN_LIMIT
        with self.assertRaisesRegex(ValueError, 'limit is .*at most 12 layers per section'):
            g.validate(plan)
    def test_a_line_can_keep_a_fixed_lane(self):
        from mnemosyne.music.orchestration import Event, Line, orchestrate
        op = {'title': 't', 'ensemble': [{'instrument': 'oboe', 'count': 2}], 'tempo': 60, 'duration': 8,
              'school': 'symphony'}
        line = Line('x', 'melody', (Event(0, 2, (69,), 64),), (69, 69), .5, None, 'oboe', 'oboe-2')
        _, assignment = orchestrate([line], op)
        self.assertEqual([p['id'] for p in assignment['players'] if p['events']], ['oboe-2'])
        self.assertEqual(g.lane_ids({'orchestra': op['ensemble']}), {'oboe': ['oboe-1', 'oboe-2']})

def tempo_map_seconds(op):
    from mnemosyne.music import tempo_map
    return tempo_map.seconds_at(op, op['quarters'])


if __name__ == '__main__':
    unittest.main()
