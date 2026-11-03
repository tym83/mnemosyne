"""Authenticated compact JSON catalogue, copied into every work's metadata."""
from copy import deepcopy
import hmac
import json

from . import DecodeError, fountain


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()


def create(encoder, work_ids):
    work_ids = list(work_ids)
    if not work_ids or any(not isinstance(w, str) or not w for w in work_ids):
        raise ValueError('nonempty work IDs required')
    if len(set(work_ids)) != len(work_ids):
        raise ValueError('one distinct work per frame required')
    body = {'version': 1, 'codec': 'SHF1', 'snapshot': encoder.snapshot.hex(),
            'k': encoder.k, 'frame_bytes': encoder.size + fountain.OVERHEAD,
            'envelope_bytes': encoder.total,
            # Position is the uint64 frame index; no repeated snapshot IDs.
            'works': work_ids}
    return {'body': body, 'mac': hmac.digest(fountain.mac_key(encoder.key),
            b'catalogue\0' + canonical(body), 'sha256').hex()}


def verify(catalogue, key):
    try:
        body = catalogue['body']
        expected = hmac.digest(fountain.mac_key(key), b'catalogue\0' + canonical(body), 'sha256').hex()
        if not hmac.compare_digest(expected, catalogue['mac']):
            raise ValueError('bad MAC')
        if body['version'] != 1 or body['codec'] != 'SHF1':
            raise ValueError('unknown catalogue')
        return body
    except (ValueError, KeyError, TypeError) as exc:
        raise DecodeError('catalogue authentication/format failed') from exc


def metadata(catalogue, index, existing=None):
    """Merge into a work metadata dict; preserve all existing artistic metadata."""
    result = deepcopy(existing or {})
    if 'backup' in result:
        raise ValueError('work already has backup metadata')
    if not 0 <= index < len(catalogue['body']['works']):
        raise ValueError('invalid catalogue index')
    work = catalogue['body']['works'][index]
    result['backup'] = {'work': work, 'index': index, 'catalogue': deepcopy(catalogue)}
    return result


def validate_work(frame, work_metadata, key):
    try:
        backup = work_metadata['backup']
        body = verify(backup['catalogue'], key)
        snapshot, index, k, size, total, _ = fountain.unpack(frame, key)
        if (snapshot.hex() != body['snapshot'] or index != backup['index']
                or body['works'][index] != backup['work'] or k != body['k']
                or size + fountain.OVERHEAD != body['frame_bytes']
                or total != body['envelope_bytes']):
            raise ValueError('work/frame mismatch')
        return body
    except (ValueError, KeyError, TypeError, IndexError) as exc:
        raise DecodeError('work metadata/frame rejected') from exc
