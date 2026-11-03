"""Small shared operations; compositional processes live in individual schools."""
from music21 import dynamics, expressions
from .common import limits


def fit(pitch, name, section):
    low, high = limits(name, section)
    while pitch < low:
        pitch += 12
    while pitch > high:
        pitch -= 12
    return pitch


def mark(part, at, text, dynamic=None):
    part.insert(at, expressions.TextExpression(text))
    if dynamic:
        for previous in list(part.getElementsByClass(dynamics.Dynamic)):
            if previous.offset == at:
                part.remove(previous)
        part.insert(at, dynamics.Dynamic(dynamic))


def grid(value):
    """Nearest 1/32 quarter (max timing error 15.6 ms at q=60)."""
    return round(float(value) * 32) / 32
