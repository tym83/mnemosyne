"""Shared instrument/ensemble contract. All input pitches are sounding MIDI."""
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from music21 import clef, instrument, interval
import yaml

ROOT = Path(__file__).parent
INSTRUMENT_DATA = yaml.safe_load((ROOT / 'instruments.yaml').read_text())
REGISTRY = INSTRUMENT_DATA['instruments']

def release_profile(name):
    spec = REGISTRY[name]
    profile = INSTRUMENT_DATA['release_profiles'].get(spec['family'])
    override = INSTRUMENT_DATA['release_overrides'].get(name, {})
    if profile is None and not override:
        raise ValueError(f'Missing release profile: {name}/{spec["family"]}')
    return {**(profile or {}), **override}

ENSEMBLE_DATA = yaml.safe_load((ROOT / 'ensembles.yaml').read_text())
ENSEMBLES = ENSEMBLE_DATA['ensembles']
LEGACY_VOICES = ENSEMBLE_DATA['legacy_voices']


@dataclass(frozen=True)
class Player:
    id: str
    instrument: str
    players: int = 1
    divisi: int = 1
    pan: float = 0

    @property
    def spec(self):
        return REGISTRY[self.instrument]


def ensemble(spec):
    """Resolve a name or [{instrument, count?, players?, divisi?, pan?}].

    Each wind/brass/percussion slot is one real player. A string section slot
    can be split into at most `divisi` independently notated desks/groups.
    """
    entries = ENSEMBLES.get(spec) if isinstance(spec, str) else spec
    if not isinstance(entries, list) or not entries:
        raise ValueError(f'Unknown or empty ensemble: {spec!r}')
    result = []
    counts = {}
    for entry in entries:
        if not isinstance(entry, dict) or entry.get('instrument') not in REGISTRY:
            raise ValueError(f'Unknown instrument: {entry}')
        name = entry['instrument']; ins = REGISTRY[name]
        count, players, divisi = (entry.get(k, 1) for k in ('count','players','divisi'))
        if any(type(n) is not int or n < 1 for n in (count, players, divisi)):
            raise ValueError('count, players and divisi must be positive integers')
        if divisi > players or (not ins['section'] and (players != 1 or divisi != 1)):
            raise ValueError(f'Invalid section/divisi for {name}')
        pan = entry.get('pan',ins['pan'])
        if not isinstance(pan,(float,int)) or not -1 <= pan <= 1:
            raise ValueError('pan must be in [-1,1]')
        for _ in range(count):
            counts[name] = counts.get(name,0)+1
            result.append(Player(f'{name}-{counts[name]}',name,players,divisi,pan))
    return result


def notation_instrument(name):
    spec = REGISTRY[name]
    obj = getattr(instrument,spec['music21'])()
    obj.instrumentName = name.replace('_',' ')
    obj.midiProgram = spec['gm_program']
    transposition = spec['sounding_minus_written']
    obj.transposition = interval.Interval(transposition) if transposition else None
    return obj


def audio_ensemble(spec):
    """Resolve playback players without replacing unavailable solo instruments."""
    players = ensemble(spec)
    for player in players:
        samples = player.spec['samples']
        if samples.get('audio_available') is False:
            raise ValueError(f'{player.instrument}: unavailable for audio; {samples["reason"]}')
    return players


def audio_contract():
    """Registry capabilities for the artist, not an artistic instrumentation choice."""
    return {
        'instruments': [n for n, s in REGISTRY.items() if s['samples'].get('audio_available') is not False],
        'unavailable': {n: s['samples']['reason'] for n, s in REGISTRY.items()
                        if s['samples'].get('audio_available') is False},
        'ensembles': {n: entries for n, entries in ENSEMBLES.items()
                      if all(REGISTRY[e['instrument']]['samples'].get('audio_available') is not False
                             for e in entries)},
        'devices': {'held_swell': 'plan-level true/false: held string, wind, brass and voice tones open after '
                    'the attack and fade before release. A deliberate expressive device, off by default.'},
        'rule': 'Use exact instrument identifiers. Solo voices cannot be rendered; '
                'choir is not a substitute for solo voices. Revise the plan yourself within these capabilities.'}


def notation_clef(name):
    return {'treble':clef.TrebleClef, 'bass':clef.BassClef, 'alto':clef.AltoClef,
            'tenor':clef.TenorClef, 'treble8vb':clef.Treble8vbClef,
            'percussion':clef.PercussionClef}[REGISTRY[name]['clefs'][0]]()


def sample_patch(name, technique):
    spec = REGISTRY[name]['samples']
    if spec.get('audio_available') is False:
        raise ValueError(f'{name}: no licensed sample available for audio; {spec["reason"]}')
    # A glissando is a continuous pitch trajectory, not a substitute sample.
    if technique == 'glissando':
        technique = 'arco' if REGISTRY[name]['family']=='strings' else 'sustain'
    patch = spec['patches'].get(technique)
    if not patch:
        raise ValueError(f'{name}: no licensed sample for {technique}; {spec.get("reason", "no substitution allowed")}')
    return spec['library'],patch


def velocity_limits(name, pitch):
    if not REGISTRY[name]['range'][0] <= pitch <= REGISTRY[name]['range'][1]:
        raise ValueError(f'{name}: out of range {pitch}')
    for zone in REGISTRY[name]['dynamic_registers']:
        if zone['range'][0] <= pitch < zone['range'][1]+1:
            return tuple(zone['velocity'])
    raise ValueError(f'{name}: out of range {pitch}')


def validate_registry():
    for name,spec in REGISTRY.items():
        low,high = spec['range']; a,b = spec['comfortable']
        if not 0 <= low <= a <= b <= high <= 127:
            raise ValueError(f'Invalid ranges: {name}')
        notation_instrument(name)
        notation_clef(name)
        for pitch in range(low,high+1):
            velocity_limits(name,pitch)
    for name in ENSEMBLES:
        ensemble(name)
