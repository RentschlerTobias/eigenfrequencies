"""Eigenfrequencies package — public API.

Modal analysis plus resonance-band penalty for one structural-mechanics mesh.
Optimization, CFD and geometry export live with the caller.
"""

from eigenfrequencies.api import (
    ModalResult,
    load_preset,
    solve_modal,
    solve_modal_penalty,
)
from eigenfrequencies.config import (
    BCConfig,
    MaterialConfig,
    MeshConfig,
    ModalAnalysisConfig,
    OutputConfig,
    ResonanceConfig,
    SolverConfig,
    WetModeConfig,
)
from eigenfrequencies.version import __version__

__all__ = [
    "BCConfig",
    "MaterialConfig",
    "MeshConfig",
    "ModalAnalysisConfig",
    "ModalResult",
    "OutputConfig",
    "ResonanceConfig",
    "SolverConfig",
    "WetModeConfig",
    "__version__",
    "load_preset",
    "solve_modal",
    "solve_modal_penalty",
]
