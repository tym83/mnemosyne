"""Mechanical reading of form: lines, syllables, rhyme ends. No judgement of quality.

Syllables are counted by vowel groups where the script makes that meaningful;
for other scripts only lines and stanzas are checked. Rhyme is a loose match of
word endings, enough to tell a rhymed line from an unrhymed one.
"""
import re

from ..weave.variants import plain

VOWELS = {
    'ru': 'аеёиоуыэюя', 'sr': 'аеиоуaeiou', 'pl': 'aeiouyąę', 'en': 'aeiouy', 'fr': 'aeiouyéèêëàâîïôûü',
    'es': 'aeiouáéíóúü', 'pt': 'aeiouáéíóúâêôãõ', 'it': 'aeiouàèéìòù', 'de': 'aeiouyäöü',
    'la': 'aeiouy', 'el': 'αεηιουωάέήίόύώϊϋ',
}


def lines(text):
    return [l.strip() for l in plain(text).splitlines() if l.strip()]


def stanzas(text):
    return [s for s in re.split(r'\n\s*\n', plain(text).strip()) if s.strip()]


def syllables(line, language):
    vowels = VOWELS.get(language)
    if vowels is None:
        return None
    return len(re.findall(f'[{vowels}]+', line.lower()))


def ending(line, size=3):
    words = re.findall(r'\w+', line.lower())
    return words[-1][-size:] if words else ''


def rhymes(a, b):
    return bool(a) and bool(b) and (ending(a) == ending(b) or ending(a, 2) == ending(b, 2))


def scheme(text_lines, pattern, problems):
    """pattern like 'xAxA' or 'ABABCDCDEFEFGG': equal letters rhyme, x is free."""
    if len(text_lines) != len(pattern):
        return
    groups = {}
    for line, mark in zip(text_lines, pattern):
        if mark != 'x':
            groups.setdefault(mark, []).append(line)
    for mark, group in groups.items():
        if any(not rhymes(group[0], other) for other in group[1:]):
            problems.append(f'lines marked {mark} do not rhyme: ' + ' / '.join(ending(l) for l in group))
