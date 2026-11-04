"""The numeric boundary and individual sensitivities. No infrastructure vocabulary.

Coefficients are explicit synthetic calibration, not aesthetic judgements.
"""
import hashlib
import math
import random

QUALITIES = ('turbulence', 'volatility', 'crowding', 'strain', 'scars', 'loss',
             'renewal', 'steadiness', 'density', 'closedness', 'age', 'abundance', 'novelty')


def qualities(value):
    """Allowlist, finite bounded numbers only; discard all accompanying facts."""
    source = value.get('qualities', value)
    result = {}
    for key in QUALITIES:
        x = source.get(key, .5 if key in ('abundance', 'novelty') else 0.)
        if isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x):
            raise ValueError('climate must contain finite numeric qualities')
        result[key] = round(max(0., min(1., x)), 3)
    return result


def temperament(identity):
    r = random.Random(int.from_bytes(hashlib.sha256(identity.encode()).digest()[:8]))
    return {k: r.uniform(.55, 1.45) for k in QUALITIES} | {'crowding_energy': r.uniform(-1, 1)}


def feel(value, profile):
    q = qualities(value)
    return {k: max(0., min(1., v * profile[k])) for k, v in q.items()}


def rhyme(today, birth):
    if not birth:
        return 0.
    a, b = qualities(today), qualities(birth)
    return max(0., 1 - sum(abs(a[k]-b[k]) for k in QUALITIES)/len(QUALITIES)) ** 3


def tendencies(value, taste, method, rng):
    """Sample suggestions, never prescribe a form or an artistic decision."""
    q = qualities(value)
    preference = temperament(str(method) + repr(taste.get('values', [])))
    axes = dict(polyphony='density', closed_form='closedness', rhythmic_irregularity='volatility',
                long_arcs='steadiness', late_style='age')
    return {name: round(rng.betavariate(1 + 4*q[key]*preference[key],
                        1 + 4*(1-q[key]) / preference[key]), 3) for name, key in axes.items()}


def year_shape(history, movements=4):
    """Equal cumulative expressive mass, not calendar-to-movement assignments."""
    if not history or not 3 <= movements <= 5:
        raise ValueError('history and 3–5 movements required')
    qs = [qualities(q) for q in history]
    tension = [(q['strain']+q['turbulence']+q['volatility'])/3 for q in qs]
    mass = [1 + t + q['renewal'] for t, q in zip(tension, qs)]
    total, cumulative, cuts = sum(mass), 0., [0.]
    target = 1
    for i, weight in enumerate(mass):
        while target < movements and cumulative + weight >= total*target/movements:
            cuts.append((i + (total*target/movements-cumulative)/weight)/len(qs))
            target += 1
        cumulative += weight
    cuts.append(1.)
    # Fixed-size abstract curve has no dates, names or event boundaries.
    curve = [round(tension[min(len(qs)-1, int(i*len(qs)/32))], 3) for i in range(32)]
    return dict(proportions=[b-a for a,b in zip(cuts, cuts[1:])], tension=curve)
