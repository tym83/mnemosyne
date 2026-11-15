"""A movement's tempo map: score time stays in quarters, performance time follows the map.

An op (orchestration plan) has `tempo` (the tempo at quarter 0) and `duration` (seconds). A movement
whose tempo changes also carries `quarters` (its length in quarters) and `tempo_map`: entries
[quarter, bpm, shown], ordered, the first at quarter 0. Each bpm holds until the next entry. `shown`
says whether the score prints the mark (a gradual change prints its first and last step and the word,
and sounds every step). Without a map the tempo is constant, exactly as before.
"""
import math


def entries(plan):
    """[(quarter, bpm, shown)] of an op; a constant tempo is a single entry."""
    raw = plan.get('tempo_map') or [[0, plan['tempo']]]
    out = []
    for item in raw:
        at, bpm = float(item[0]), float(item[1])
        shown = bool(item[2]) if len(item) > 2 else True
        out.append((at, bpm, shown))
    if out[0][0] != 0 or any(b[0] <= a[0] for a, b in zip(out, out[1:])):
        raise ValueError('tempo_map must start at quarter 0 and increase')
    if any(not math.isfinite(bpm) or bpm <= 0 for _, bpm, _ in out):
        raise ValueError('tempo_map tempi must be positive and finite')
    return out


def total_quarters(plan):
    """Length of the op in quarters."""
    if plan.get('tempo_map'):
        return float(plan['quarters'])
    return plan['duration'] * plan['tempo'] / 60


def bpm_at(plan, quarter):
    bpm = None
    for at, value, _ in entries(plan):
        if at <= quarter + 1e-9:
            bpm = value
    return bpm


def seconds_at(plan, quarter):
    """Performance seconds from the start to `quarter`."""
    marks = entries(plan)
    seconds = 0.
    for (at, bpm, _), nxt in zip(marks, marks[1:] + [(math.inf, None, None)]):
        if quarter <= at:
            break
        seconds += (min(quarter, nxt[0]) - at) * 60 / bpm
    return seconds


def quarter_at(plan, seconds):
    """Score quarter reached after `seconds` of performance (inverse of seconds_at)."""
    marks = entries(plan)
    elapsed = 0.
    for (at, bpm, _), nxt in zip(marks, marks[1:] + [(math.inf, None, None)]):
        span = (nxt[0] - at) * 60 / bpm
        if seconds <= elapsed + span:
            return at + (seconds - elapsed) * bpm / 60
        elapsed += span
    raise AssertionError('unreachable')


def section_steps(start, quarters, tempo, tempo_to=None):
    """Map entries for one section: one tempo, or a linear change sounding one step per quarter note.

    Quarter k of the n quarters a section spans (the last may be partial) is played at
    tempo + (tempo_to - tempo) * k / (n - 1): the first quarter at `tempo`, the last at `tempo_to`.
    """
    if tempo_to is None or tempo_to == tempo:
        return [(start, float(tempo), True)]
    n = math.ceil(quarters - 1e-9)
    if n <= 1:
        return [(start, float(tempo), True)]
    return [(start + k, float(tempo + (tempo_to - tempo) * k / (n - 1)), k in (0, n - 1)) for k in range(n)]


def section_seconds(quarters, tempo, tempo_to=None):
    """Seconds of a section under section_steps."""
    steps = section_steps(0., quarters, tempo, tempo_to)
    total = 0.
    for (at, bpm, _), nxt in zip(steps, steps[1:] + [(quarters, None, None)]):
        total += (nxt[0] - at) * 60 / bpm
    return total
