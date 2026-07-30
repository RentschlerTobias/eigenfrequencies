"""Optimization package: ask/tell protocol + DE, CMA-ES, BO, and PSO backends."""

from eigenfrequencies.optimize.backends.bo import BOOptimizer
from eigenfrequencies.optimize.backends.cmaes import CMAESOptimizer
from eigenfrequencies.optimize.backends.de import DEOptimizer
from eigenfrequencies.optimize.backends.pso import PSOOptimizer
from eigenfrequencies.optimize.islands import CheckpointError, IslandOptimizer
from eigenfrequencies.optimize.protocol import (
    Design,
    Optimizer,
    ProtocolUsageError,
    create,
    register,
)

register("de", lambda cfg: DEOptimizer(cfg))
register("cmaes", lambda cfg: CMAESOptimizer(cfg))
register("bo", lambda cfg: BOOptimizer(cfg))
register("pso", lambda cfg: PSOOptimizer(cfg))

__all__ = [
    "BOOptimizer",
    "CheckpointError",
    "CMAESOptimizer",
    "create",
    "DEOptimizer",
    "Design",
    "IslandOptimizer",
    "Optimizer",
    "PSOOptimizer",
    "ProtocolUsageError",
    "register",
]
