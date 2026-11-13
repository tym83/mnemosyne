"""Shared mechanical reading for the prose schools: length in words (CJK-aware) and paragraphs."""
import re

from ..form import stanzas
from ..founding import words

SENTENCE_END = re.compile(r'[.!?…。！？]+')


def length_problems(text, frame):
    n = words(text)
    problems = []
    if n < frame['min_words'] * .9:
        problems.append(f'{n} words; at least {frame["min_words"]}')
    if n > frame['max_words'] * 1.1:
        problems.append(f'{n} words; at most {frame["max_words"]}')
    return problems


def paragraph_problems(text, minimum, what='paragraphs'):
    found = len(stanzas(text))
    return [f'at least {minimum} {what} separated by blank lines expected, found {found}'] if found < minimum else []


def longest_sentence(text):
    return max((words(s) for s in SENTENCE_END.split(text)), default=0)


def headings(text):
    """Short lines standing alone between blank lines, without closing punctuation: names of speakers, titles."""
    found = []
    for block in stanzas(text):
        lines = [l for l in block.splitlines() if l.strip()]
        if len(lines) != 1:
            continue
        line = re.sub(r'^[#*_\s]+|[#*_\s:：]+$', '', lines[0])
        if line and words(line) <= 6 and len(line) <= 40 and not SENTENCE_END.search(line):
            found.append(line)
    return found
