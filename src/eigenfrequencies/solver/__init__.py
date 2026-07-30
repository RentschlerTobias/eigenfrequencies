"""Eigenfrequencies solver package — public API."""

from eigenfrequencies.solver.core import ModalSolver
from eigenfrequencies.solver.exceptions import SolverConfigError
from eigenfrequencies.solver.rayleigh import rayleigh_refine

__all__ = [
    "ModalSolver",
    "SolverConfigError",
    "rayleigh_refine",
]
