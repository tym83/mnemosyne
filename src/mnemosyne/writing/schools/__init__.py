"""Literature schools as code.

Each school is a module with:
  KIND        'poetry' or 'prose'
  RULES       the form in a few sentences, for the writer
  skeleton(plan, rng) -> dict   the deterministic frame of one work
  check(text, frame, language) -> list[str]   mechanical form problems, empty when the form holds
  EXAMPLE_PLAN  a complete plan

The writer fills the frame in their own language, with their own variants;
the school never writes words and never judges their worth.
"""
from . import haiku, chastushka, sonnet, bylina, fairy_tale, eluard, pavic, minimalism

SCHOOLS = {m.__name__.rsplit('.', 1)[-1]: m for m in
           (haiku, chastushka, sonnet, bylina, fairy_tale, eluard, pavic, minimalism)}
