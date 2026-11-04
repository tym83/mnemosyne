"""Read-only transport preflight; the implemented music channel is in nocturne.py.

    uv run python -m mnemosyne.weave.music

Reports actual transport sizes, never claims that a score carries the bytes.
"""
import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import zlib

from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey
from music21 import chord, converter, voiceLeading

from mnemosyne.architecture import state_at
from . import arithmetic, payload


def canonical(obj):
    return json.dumps(obj, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()


def style_check(score):
    """Crude staff-envelope diagnostics, not a contrapuntal/style judgment.

    Crossings: upper staff minimum below lower staff maximum at event onsets.
    Parallels: outermost pitches in adjacent chordified sonorities, including
    only music21's parallel fifth/octave classification. This ignores inner
    contrapuntal voices, and counts attacks rather than durations.
    """
    events = []
    ranges = []
    for part in score.parts:
        notes = list(part.recurse().notes)
        events.append([(n.getOffsetInHierarchy(part), n.getOffsetInHierarchy(part) + n.quarterLength,
                        tuple(p.midi for p in n.pitches)) for n in notes])
        pitches = [p.midi for n in notes for p in n.pitches]
        ranges.append([min(pitches), max(pitches)] if pitches else None)
    crossings = 0
    if len(events) == 2:
        for onset in sorted({a for staff in events for a, _, _ in staff}):
            active = [[p for a, b, ps in staff if a <= onset < b for p in ps] for staff in events]
            crossings += bool(all(active) and min(active[0]) < max(active[1]))
    fifths = octaves = 0
    sonorities = [sorted(n.pitches, key=lambda p: p.ps) for n in score.chordify().recurse().notes]
    for before, after in zip(sonorities, sonorities[1:]):
        if len(before) >= 2 and len(after) >= 2:
            quartet = voiceLeading.VoiceLeadingQuartet(before[-1], after[-1], before[0], after[0])
            fifths += bool(quartet.parallelFifth())
            octaves += bool(quartet.parallelOctave())
    return {'staff_ranges_midi': ranges, 'staff_crossing_onsets': crossings,
            'outer_parallel_fifths': fifths, 'outer_parallel_octaves': octaves,
            'definition': style_check.__doc__}


def preflight(xml, ops):
    state = state_at(ops, datetime.fromisoformat('2025-07-01T00:00:00+00:00'))
    objects = [obj for (kind, _, _), obj in sorted(state.items()) if kind != 'Secret']
    raw_state = canonical(objects)
    # A complete Namespace is a real, independently interpretable state fragment.
    namespace = next(obj for obj in objects if obj['kind'] == 'Namespace' and obj['metadata']['name'] == 'shop')
    data = canonical(namespace)
    score = converter.parse(str(xml))
    key = X25519PrivateKey.generate()  # ephemeral preflight only; never published
    context = xml.read_bytes()
    frame = payload.seal(data, key.public_key(), context=context)
    recovered = payload.open_envelope(frame, key, context=context)
    if recovered != data:
        raise RuntimeError('payload round trip failed')
    bars = len(list(score.parts[0].getElementsByClass('Measure')))
    seconds = sum(float(b-a)*60/m.getQuarterBPM() for a, b, m in score.metronomeMarkBoundaries())
    expanded = score.expandRepeats()
    playback = sum(float(b-a)*60/m.getQuarterBPM() for a, b, m in expanded.metronomeMarkBoundaries())
    lower = list(score.parts[1].recurse().notes)
    inner = sum(len(n.pitches)-1 for n in lower if isinstance(n, chord.Chord))
    return {
        'status': 'preflight_only_no_music_channel', 'source': str(xml),
        'state_at': '2025-07-01T00:00:00+00:00', 'state_objects_excluding_secrets': len(objects),
        'state_canonical_json_bytes': len(raw_state), 'state_zlib_bytes': len(zlib.compress(raw_state, 9)),
        'fragment': 'Namespace/shop', 'payload_bytes': len(data),
        'payload_sha256': hashlib.sha256(data).hexdigest(),
        'compressed_bytes': len(zlib.compress(data, 9)), 'frame_bytes': len(frame),
        'fragment_percent_of_canonical_state_bytes': 100*len(data)/len(raw_state),
        'payload_round_trip': recovered == data, 'opus_round_trip': False,
        'bars': bars, 'score_seconds': seconds, 'playback_seconds_with_repeats': playback,
        'required_frame_bits_per_written_bar': len(frame)*8/bars,
        'required_frame_bits_per_score_minute': len(frame)*8*60/seconds,
        'required_frame_bits_per_playback_minute': len(frame)*8*60/playback,
        'lower_staff_chords': sum(isinstance(n, chord.Chord) for n in lower),
        'non_bass_chord_tones': inner,
        'hypothetical_one_binary_choice_per_non_bass_tone_bytes': arithmetic.capacity([2]*inner),
        'original_style': style_check(score),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--xml', type=Path, default=Path('out/works/music/nocturne/p02_000.xml'))
    parser.add_argument('--ops', type=Path, default=Path('out/scenarios/shop/ops.jsonl'))
    args = parser.parse_args()
    print(json.dumps(preflight(args.xml, args.ops), indent=2, ensure_ascii=False))


if __name__ == '__main__':
    main()
