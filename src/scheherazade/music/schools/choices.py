"""Injectable randomness for the existing school grammars.

This is a forward-generation interface, not an invertible music channel.
Several grammars discard random outcomes or have less than a byte of entropy.
An arithmetic source alone cannot make those grammars carry an envelope.
"""
import random
from collections.abc import MutableSequence, Sequence
from typing import Protocol, TypeVar

T = TypeVar('T')


class ChoiceSource(Protocol):
    def choice(self, seq: Sequence[T]) -> T: ...
    def randrange(self, start: int, stop: int | None = None, step: int = 1) -> int: ...
    def sample(self, population: Sequence[T], k: int) -> list[T]: ...
    def shuffle(self, x: MutableSequence[T]) -> None: ...
    def random(self) -> float: ...
    def expovariate(self, lambd: float = 1.0) -> float: ...


class SeededChoices(random.Random):
    """Unmodified Python RNG: preserve draw order and seeded musical output."""
