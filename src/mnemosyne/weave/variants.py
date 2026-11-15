"""Variant readings: the data lives in which of the author's own variants remains.

A writer's draft hesitates: {cold|grey|still} sea. The night's texts keep those
hesitations as an apparatus of variants (markup), and the reading text keeps
one variant per place. Which one remains is the carrier, chosen by the
arithmetic coder from the frames. A reader who has the apparatus and the text
recovers the choices, the bytes and, with the key, the frames.

Variants at one place must be distinct, and none may be a prefix of another:
then the reading text identifies the chosen variant without ambiguity.
The apparatus and the reading texts are authenticated together.
"""
import hmac
import json
import re
import struct

from . import DecodeError, arithmetic
from .codecs.v1 import fountain

CODEC = 'mnemosyne-variants-v1'
DOMAIN = b'mnemosyne/variants/v1\0'
OVERHEAD = 20
PLACE = re.compile(r'\{([^{}]*)\}')
MAX_OPTIONS = 8


def places(markup: str):
    """[(literal, options)...] + trailing literal; malformed places are ordinary text."""
    pieces, cursor = [], 0
    for match in PLACE.finditer(markup):
        options = match.group(1).split('|')
        if not valid(options):
            continue
        pieces.append((markup[cursor:match.start()], options))
        cursor = match.end()
    return pieces, markup[cursor:]


def valid(options):
    return (2 <= len(options) <= MAX_OPTIONS and all(o.strip() for o in options)
            and len(set(options)) == len(options)
            and not any(a != b and b.startswith(a) for a in options for b in options))


def plain(markup: str) -> str:
    """The first variant everywhere: how the draft reads before the night is woven."""
    pieces, tail = places(markup)
    return ''.join(lit + opts[0] for lit, opts in pieces) + tail


def radices(entries):
    return [len(opts) for e in entries for _, opts in places(e['markup'])[0]]


def capacity(entries):
    r = radices(entries)
    return arithmetic.capacity(r) if r else 0


def context(entries):
    return DOMAIN + json.dumps([[e['id'], e['markup']] for e in entries], ensure_ascii=False,
                               separators=(',', ':')).encode()


def realize(entries, digits):
    out, it = [], iter(digits)
    for e in entries:
        pieces, tail = places(e['markup'])
        out.append({**e, 'text': ''.join(lit + opts[next(it)] for lit, opts in pieces) + tail})
    return out


def read(entry):
    """Digits chosen in one reading text, by its own apparatus."""
    pieces, tail = places(entry['markup'])
    text, at, digits = entry['text'], 0, []
    for lit, opts in pieces:
        if not text.startswith(lit, at):
            raise DecodeError('reading text departs from its apparatus')
        at += len(lit)
        found = [i for i, o in enumerate(opts) if text.startswith(o, at)]
        if len(found) != 1:
            raise DecodeError('reading text does not choose one variant')
        digits.append(found[0])
        at += len(opts[found[0]])
    if text[at:] != tail:
        raise DecodeError('reading text departs from its apparatus')
    return digits


def encode_many(entries, frames, key):
    frames = list(frames)
    if not frames or len({len(f) for f in frames}) != 1:
        raise ValueError('nonempty equal-sized fountain frames required')
    size = capacity(entries)
    if sum(map(len, frames)) + OVERHEAD > size:
        raise ValueError('frames exceed the variants of this volume')
    body = (struct.pack('>II', len(frames[0]), len(frames)) + b''.join(frames)).ljust(size - 12, b'\0')
    tag = hmac.digest(fountain.mac_key(key), context(entries) + body, 'sha256')[:12]
    return {'codec': CODEC, 'entries': realize(entries, arithmetic.encode(body + tag, radices(entries)))}


def decode_many(volume, key):
    try:
        if volume.get('codec') != CODEC:
            raise DecodeError('not a variants volume')
        entries = volume['entries']
        digits = [d for e in entries for d in read(e)]
        block = arithmetic.decode(digits, radices(entries), capacity(entries))
    except (KeyError, TypeError, AttributeError, ValueError) as exc:
        raise DecodeError('invalid variants volume') from exc
    body, tag = block[:-12], block[-12:]
    expected = hmac.digest(fountain.mac_key(key), context(entries) + body, 'sha256')[:12]
    if not hmac.compare_digest(tag, expected):
        raise DecodeError('variants volume authentication failed')
    size, count = struct.unpack('>II', body[:8])
    end = 8 + size * count
    if not fountain.OVERHEAD < size or count < 1 or end > len(body) or any(body[end:]):
        raise DecodeError('invalid variants length/padding')
    return [body[i:i+size] for i in range(8, end, size)]


# Typographic places: a space between two words is set as an ordinary space, a no-break space or
# a narrow no-break space. A reader sees the same words; the setting carries the data. Every prose
# text of the night carries this way: drafts, works, notebooks, reviews, Lives, translations.
SPACES = (' ', '\u00a0', '\u202f')
WORD = re.compile(r'(?<=\w) (?=\w)')
MIN_PROSE = 120


def prose(text):
    """A text of words that can be typeset: long enough, not JSON or markup of its own."""
    return (isinstance(text, str) and len(text) >= MIN_PROSE and text.count(' ') >= 12
            and text.lstrip()[:1] not in ('{', '[') and not any(c in text for c in '{}|'))


def typeset(text):
    """Markup whose places are the word spaces of a prose text (each option carries its next word)."""
    if not prose(text) or places(text)[0]:
        return text
    out, cursor = [], 0
    spans = [m.start() for m in WORD.finditer(text)]
    for i, at in enumerate(spans):
        end = spans[i + 1] if i + 1 < len(spans) else len(text)
        word = re.match(r'\w+', text[at + 1:end]).group(0)
        out.append(text[cursor:at])
        out.append('{' + '|'.join(sp + word for sp in SPACES) + '}')
        cursor = at + 1 + len(word)
    out.append(text[cursor:])
    return ''.join(out)


def collect(record, prefix=''):
    """Every string in a notebook record that carries a variant place, with its path."""
    found = []
    if isinstance(record, dict):
        for k in sorted(record):
            found += collect(record[k], f'{prefix}/{k}')
    elif isinstance(record, list):
        for i, v in enumerate(record):
            found += collect(v, f'{prefix}/{i}')
    elif isinstance(record, str) and places(record)[0]:
        found.append({'id': prefix, 'markup': record})
    elif prose(record):
        found.append({'id': prefix, 'markup': typeset(record)})
    return found
