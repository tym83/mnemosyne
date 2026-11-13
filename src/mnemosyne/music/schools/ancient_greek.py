"""Greek monody: tetrachords in three genera, an octave species, long/short feet, lyre/aulos heterophony."""
from music21 import stream
from .choices import ChoiceSource
from .common import ENSEMBLES, setup, limits, put, finish
from .material import mark

# Lower-to-upper divisions of a fourth (semitones), after Aristoxenus' simplest shades.
GENERA = {'diatonic': (1, 2, 2), 'chromatic': (1, 1, 3), 'enharmonic': (.5, .5, 4)}
CHARACTER_GENUS = {'still': 'enharmonic', 'dissolving': 'enharmonic', 'agitated': 'chromatic',
                   'flowing': 'diatonic', 'luminous': 'diatonic'}
# Octave species named by their lowest note on the white-key Dorian system (E-e).
HARMONIAI = {'Mixolydian': 11, 'Lydian': 0, 'Phrygian': 2, 'Dorian': 4,
             'Hypolydian': 5, 'Hypophrygian': 7, 'Hypodorian': 9}
SHORT, LONG, TRISEME = .5, 1, 1.5
FEET = {'iamb': (SHORT, LONG), 'trochee': (LONG, SHORT), 'dactyl': (LONG, SHORT, SHORT),
        'anapaest': (SHORT, SHORT, LONG), 'spondee': (LONG, LONG)}


def system(genus, base):
    """Two disjunct tetrachords (E-A, B-e pattern) in a genus, repeated over every octave."""
    steps = GENERA[genus]
    octave = [0]
    for _ in range(2):
        for s in steps:
            octave.append(octave[-1]+s)
        if len(octave) == 4:
            octave.append(octave[-1]+2)  # tone of disjunction
    degrees = octave[:-1]
    return sorted({base+12*k+d for k in range(-11, 12) for d in degrees})


def line(metre, feet):
    pattern = [v for _ in range(feet) for v in FEET[metre]]
    pattern[-1] = TRISEME
    return pattern


def nearest(own, pitch, shift):
    """The same note (or its consonance) in this instrument's octave; else the closest playable."""
    same = [p for p in own if (p-pitch-shift) % 12 == 0]
    return min(same or own, key=lambda p: (abs(p-(pitch+shift)), p))


def compose(plan: dict, seed: int, *, choices: ChoiceSource | None = None) -> stream.Score:
    score, rng, sections, total = setup(plan, seed, 'ancient_greek', choices=choices)
    harmonia = rng.choice(sorted(HARMONIAI))
    # Dorian tetrachord frame on E; a tonos transposes the whole system.
    tonos = int(plan.get('tonic', 64)) - 64 + rng.choice([0, 2, -3])
    names = ENSEMBLES[plan['ensemble']]
    for start, end, sec in sections:
        genus = CHARACTER_GENUS[sec['character']]
        gamut = system(genus, 4+tonos)
        species = (HARMONIAI[harmonia]+tonos) % 12
        low, high = limits(names[0], sec)
        voice = [p for p in gamut if low <= p <= high and (names[0] != 'piano' or p == int(p))]
        centre = min(range(len(voice)), key=lambda j: abs(voice[j]-(low+high)/2))
        finals = [j for j, p in enumerate(voice) if round(p) % 12 == species]
        home = min(finals, key=lambda j: abs(j-centre)) if finals else centre
        for i, part in enumerate(score.parts):
            mark(part, start, f'{harmonia} harmonia, {genus} genus; '
                 + ('song (aulos)' if i == 0 else 'heterophony' if i % 2 else 'lyre below the song'))
        at, j = start, home
        while at < end:
            metre = rng.choice(sorted(FEET))
            rhythm = line(metre, rng.randrange(3, 6))
            melody = []
            for k, length in enumerate(rhythm):
                if k == len(rhythm)-1:
                    j = home
                elif length >= LONG or rng.random() < .7:
                    j = max(0, min(len(voice)-1, j+rng.choice([-1, 1])))
                else:
                    j = max(0, min(len(voice)-1, j+rng.choice([-3, -2, 2, 3])))
                melody.append((at, min(length, end-at), j))
                at += length
                if at >= end:
                    break
            at += SHORT  # breath between lines
            for i, (part, name) in enumerate(zip(score.parts, names)):
                plow, phigh = limits(name, sec)
                own = [p for p in gamut if plow <= p <= phigh]
                if name == 'piano':
                    # A keyboard cannot sound quarter tones; it plucks only the fixed notes.
                    own = [p for p in own if p == int(p)]
                for k, (t, length, jj) in enumerate(melody):
                    pitch = voice[jj]
                    if i == 0:
                        put(part, t, length, pitch)
                        continue
                    shift = 0 if i == 1 else -12 if i < len(names)-1 else -24
                    if i % 2 == 0 and length < LONG and k != len(melody)-1:
                        continue  # the lyre strikes long syllables only
                    if i % 2 == 0 and k % 3 == 1:
                        shift -= 5  # a fourth below the song: lyre consonance
                    elif i % 2 and length >= LONG and k % 2:
                        # Aulos heterophony: the long syllable splits into note + upper neighbour.
                        target = nearest(own, pitch, shift)
                        up = [p for p in own if p > target]
                        put(part, t, length/2, target)
                        put(part, t+length/2, length/2, min(up, key=lambda p: p-target) if up else target)
                        continue
                    target = nearest(own, pitch, shift)
                    put(part, t, length*(.75 if i % 2 == 0 else 1), target)
    return finish(score, total)


# Authorized performance freedom; the note grammar above remains invariant.
FREE_CHANNELS = {'dynamics': 'Genus, species and long/short feet remain fixed; the stress of each syllable is free.', 'period_quarters': 0.5, 'levels': 16, 'step_percent': 0.25, 'max_deviation_percent': 1.875}
