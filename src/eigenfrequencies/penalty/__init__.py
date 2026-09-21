"""Penalty subpackage — public API.

Only the resonance band penalty lives here; scaling/combination with other
objectives is the caller's responsibility.
"""

from eigenfrequencies.penalty.band import band_report, compute_penalty, violating_modes

__all__ = [
    "band_report",
    "compute_penalty",
    "violating_modes",
]
