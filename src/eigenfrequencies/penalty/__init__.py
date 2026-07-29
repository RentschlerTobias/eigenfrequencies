"""Penalty subpackage — public API."""

from eigenfrequencies.penalty.band import band_report, compute_penalty
from eigenfrequencies.penalty.objective import (
    cfd_scalar,
    combined_objective,
    resonance_term,
)

__all__ = [
    "band_report",
    "compute_penalty",
    "cfd_scalar",
    "combined_objective",
    "resonance_term",
]
