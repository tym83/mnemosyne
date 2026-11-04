"""Deterministic rule composers; plan duration and section durations are seconds."""
from . import tintinnabuli, stochastic, micropolyphony, serial
SCHOOLS = {m.__name__.rsplit('.',1)[-1]:m for m in (tintinnabuli,stochastic,micropolyphony,serial)}

from . import feldman, process, additive, in_c, spectral, sonorism, messiaen, ustvolskaya, chance, tempo_canon, aleatoric_counterpoint, fibonacci, polystylism, scelsi, drone
SCHOOLS.update({m.__name__.rsplit(".", 1)[-1]: m for m in (feldman, process, additive, in_c, spectral, sonorism, messiaen, ustvolskaya, chance, tempo_canon, aleatoric_counterpoint, fibonacci, polystylism, scelsi, drone)})
