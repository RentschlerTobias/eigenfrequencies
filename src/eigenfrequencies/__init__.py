"""Eigenfrequencies package — public API."""

from eigenfrequencies.config import (
    BCConfig,
    CFDConfig,
    DEConfig,
    DesignConfig,
    MaterialConfig,
    MeshConfig,
    ObjectiveConfig,
    OptimizationConfig,
    OutputConfig,
    SolverConfig,
    WetModeConfig,
)
from eigenfrequencies.version import __version__

__all__ = [
    "BCConfig",
    "CFDConfig",
    "DEConfig",
    "DesignConfig",
    "MaterialConfig",
    "MeshConfig",
    "ObjectiveConfig",
    "OptimizationConfig",
    "OutputConfig",
    "SolverConfig",
    "WetModeConfig",
    "__version__",
]
