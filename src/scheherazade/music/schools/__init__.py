"""Deterministic rule composers; plan duration and section durations are seconds."""
from . import tintinnabuli, stochastic, micropolyphony, serial
SCHOOLS = {m.__name__.rsplit('.',1)[-1]:m for m in (tintinnabuli,stochastic,micropolyphony,serial)}
