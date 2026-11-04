"""Reversible timing carrier for a synthetic listening panel, codec version 1.

Each sampled session has a fixed second and uniform 0..255 ms scheduling jitter.
A keyed pad preserves that distribution even for structured frame headers.
Counts, ratings, charts, programme, ordering and seconds are unchanged.
"""
from copy import deepcopy
import hashlib
import hmac

from . import DecodeError, catalogue, fountain


def capacity(log):
    return len(log['timestamps_ms'])


def _pad(log, key):
    context = {k: v for k,v in log.items() if k not in ('timestamps_ms', 'backup')}
    context['slots'] = [t // 1000 for t in log['timestamps_ms']]
    seed = hmac.digest(fountain.mac_key(key), b'audience-timing-v1\0' + catalogue.canonical(context), 'sha256')
    return hashlib.shake_256(seed).digest(capacity(log))


def encode(log, frame, key, manifest, index):
    if len(frame) != capacity(log):
        raise ValueError('frame must fill the panel timing capacity')
    catalogue.validate_work(frame, catalogue.metadata(manifest, index), key)
    pad = _pad(log, key)
    result = deepcopy(log)
    result['timestamps_ms'] = [t//1000*1000 + (b ^ p) for t,b,p in zip(log['timestamps_ms'], frame, pad)]
    result.update(catalogue.metadata(manifest, index))
    return result


def decode(log, key):
    times = log['timestamps_ms']
    if any(type(t) is not int or t < 0 or t % 1000 > 255 for t in times):
        raise DecodeError('invalid panel timing')
    frame = bytes(t%1000 ^ p for t,p in zip(times, _pad(log, key)))
    catalogue.validate_work(frame, log, key)
    return frame


def pack(logs, data, key, loss=.3):
    """Embed a snapshot in existing logs; never invent listening to gain capacity.

    Keys are supplied by the caller and are never persisted. Encryption uses
    fresh randomness; fate and the unencoded logs remain deterministic.
    """
    from . import payload
    usable = [log for log in logs if capacity(log) > fountain.OVERHEAD]
    if not usable:
        raise ValueError('no audience capacity')
    size = capacity(usable[0])
    usable = [log for log in usable if capacity(log) == size]
    envelope = payload.seal(data, key.public_key(), context=fountain.DOMAIN)
    count = fountain.recommended_count(len(envelope), size, loss)
    if len(usable) < count:
        raise ValueError(f'need {count} audience logs, have {len(usable)}')
    chosen = usable[:count]
    encoder = fountain.Encoder(envelope, size, key)
    manifest = catalogue.create(encoder, [log['id'] for log in chosen])
    return [encode(log, encoder.frame(i), key, manifest, i) for i,log in enumerate(chosen)]


def recover(logs, key):
    return fountain.recover([decode(log, key) for log in logs], key)
