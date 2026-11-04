"""Measure erasure tolerance at work boundaries, not individual frame boundaries."""
import itertools
import math
from mnemosyne.weave import fountain


def check(batches, key, *, fraction=.30, max_subsets=10000):
    n = len(batches)
    lost = math.ceil(n*fraction)
    retained = n-lost
    combinations = math.comb(n, retained)
    result = {'works': n, 'lost': lost, 'retained': retained, 'subsets': combinations,
              'loss_tolerance_verified': False}
    if retained < 1 or combinations > max_subsets:
        result['reason'] = 'not enough works' if retained < 1 else 'exhaustive subset budget exceeded'
        return result
    masks, expected = [], None
    for batch in batches:
        rows = []
        for frame in batch:
            snapshot, index, k, size, total, _ = fountain.unpack(frame, key)
            dimensions = snapshot, k, size, total
            if expected is not None and dimensions != expected:
                raise ValueError('mixed snapshots in loss check')
            expected = dimensions
            rows.append(fountain.coefficients(snapshot, index, k))
        masks.append(rows)
    if expected is None:
        return result
    required = expected[1]
    minimum = required
    for selected in itertools.combinations(range(n), retained):
        pivots = {}
        for mask in (m for i in selected for m in masks[i]):
            while mask:
                pivot = mask.bit_length()-1
                if pivot not in pivots:
                    pivots[pivot] = mask
                    break
                mask ^= pivots[pivot]
        minimum = min(minimum, len(pivots))
    result.update(minimum_rank=minimum, required_rank=required,
                  loss_tolerance_verified=minimum >= required)
    return result
