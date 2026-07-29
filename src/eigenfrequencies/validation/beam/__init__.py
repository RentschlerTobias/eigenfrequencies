"""Beam validation package."""

from eigenfrequencies.validation.beam.analytical import (
    analytical_frequencies,
    analytical_frequencies_cantilever,
    compute_alpha_values,
)

__all__ = [
    "analytical_frequencies",
    "analytical_frequencies_cantilever",
    "compute_alpha_values",
]
