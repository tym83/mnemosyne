"""The margins of a writer's notebook: lines of their own words, set down beside the work (§57.4).

No model writes them. A deterministic grammar draws on the writer's vocabulary (the words of their
works and notebooks, in their own language) and lays out short lines; each place in a line is a
choice among eight of their words. The choice that remains is the carrier, through the same
variant-reading codec as every text of the night: the margin is the apparatus, the reading is what
stays on the page.
"""
import hashlib
import random
import re

from mnemosyne.weave import variants

WORD = re.compile(r'\w{3,}', re.UNICODE)
OPTIONS = 8  # the variant codec allows up to eight readings at a place
LINES = 100


def vocabulary(texts, limit=400):
    """The writer's own words, most frequent first, without duplicates up to case."""
    counts = {}
    for text in texts:
        for w in WORD.findall(text or ''):
            key = w.lower()
            counts[key] = counts.get(key, 0) + 1
    return [w for w, _ in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))][:limit]


def places_from(words, rng):
    """One place: eight of the writer's words, none a prefix of another (so a reading is unambiguous)."""
    chosen = []
    for w in rng.sample(words, min(len(words), OPTIONS * 4)):
        if all(not a.startswith(w) and not w.startswith(a) for a in chosen):
            chosen.append(w)
        if len(chosen) == OPTIONS:
            break
    return chosen if len(chosen) >= 2 else None


def page(texts, seed, lines=LINES):
    """A page of margin lines as variant markup; empty when the writer has too few words yet."""
    words = vocabulary(texts)
    if len(words) < OPTIONS * 2:
        return ''
    rng = random.Random(int.from_bytes(hashlib.sha256(seed.encode()).digest()[:8], 'big'))
    out = []
    for _ in range(lines):
        line = []
        for _ in range(rng.randint(4, 8)):
            options = places_from(words, rng)
            if options:
                line.append('{' + '|'.join(options) + '}')
        out.append(' '.join(line))
    markup = '\n'.join(out)
    assert all(variants.valid(opts) for _, opts in variants.places(markup)[0])
    return markup


def writer_texts(artist, record=None):
    """What a writer has written so far: works, ideas, drafts and tonight's notebook."""
    texts = []
    for w in artist.catalogue:
        texts += [w.get('excerpt'), w.get('idea'), w.get('title'), w.get('diary')]
    if record:
        texts += [record.get('statement', {}).get('idea') if isinstance(record.get('statement'), dict) else None]
        final = record.get('final')
        if isinstance(final, dict):
            texts.append(final.get('text'))
        for d in record.get('drafts') or []:
            if isinstance(d, dict):
                texts.append(d.get('text'))
    return [t for t in texts if isinstance(t, str)]
