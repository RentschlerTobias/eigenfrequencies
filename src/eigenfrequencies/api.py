"""Public modal-analysis API.

One solving entry point: ``solve_modal(msh_path, config)``. It reads a
structural-mechanics mesh, runs the modal analysis, and returns the raw
(unweighted) resonance penalty together with the frequencies and diagnostics.

The module imports without dolfinx: the heavy mesh/solver imports happen
inside ``solve_modal`` so that config/preset helpers stay usable in a
light-weight environment.
"""

from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Mapping, Optional, Union

from eigenfrequencies.config import (
    ModalAnalysisConfig,
    ResonanceConfig,
)
from eigenfrequencies.penalty.band import (
    band_report,
    compute_penalty,
    violating_modes,
)

__all__ = [
    "ModalResult",
    "solve_modal",
    "solve_modal_penalty",
    "load_preset",
]


@dataclass(frozen=True)
class ModalResult:
    """Outcome of one modal-analysis + penalty evaluation.

    Attributes:
        frequencies_hz: Dry eigenfrequencies in Hz (ascending, as solved)
        resonance_penalty: Raw, unweighted penalty (penalty_k = 1); 0.0 when no
            mode sits in a forbidden band
        violating_modes: 1-based indices of modes inside a forbidden band
        band_report: Human-readable violation summary
        metadata: Context for logging (mesh path, n_rpm, bands, backend, ...)
    """

    frequencies_hz: tuple
    resonance_penalty: float
    violating_modes: tuple
    band_report: str
    metadata: dict = field(default_factory=dict)


def solve_modal(
    msh_path: Union[str, Path],
    config: ModalAnalysisConfig,
) -> ModalResult:
    """Run modal analysis on ``msh_path`` and compute the resonance penalty.

    ``config.mesh.msh_path`` / ``step_path`` are overridden by ``msh_path``;
    the mesh is scaled by ``config.mesh.scale_factor`` before solving (only
    when it differs from 1.0).
    """
    from eigenfrequencies.io.load import load_and_prepare_mesh
    from eigenfrequencies.solver.core import ModalSolver

    mesh_cfg = replace(config.mesh, msh_path=str(msh_path))
    domain = load_and_prepare_mesh(mesh_cfg)

    if mesh_cfg.scale_factor != 1.0:
        domain.geometry.x[:, :] *= mesh_cfg.scale_factor

    solver = ModalSolver(domain, config.material, config.bc, config.solver)
    eigenvalues, vectors = solver.solve()
    frequencies = ModalSolver.compute_frequencies(eigenvalues)

    penalty = compute_penalty(frequencies, config.resonance)
    violators = violating_modes(frequencies, config.resonance)
    report = band_report(frequencies, config.resonance)

    metadata: dict[str, Any] = {
        "msh_path": str(msh_path),
        "n_rpm": config.resonance.n_rpm,
        "Z_guidevanes": config.resonance.Z_guidevanes,
        "max_harmonic": config.resonance.max_harmonic,
        "margin_hz": config.resonance.margin_hz,
        "margin_fraction": config.resonance.margin_fraction,
        "solver_backend": solver.backend_used or config.solver.solver_backend,
        "num_eigenvalues": config.solver.num_eigenvalues,
        "element_degree": config.solver.element_degree,
        "n_modes": int(len(frequencies)),
        "scale_factor": mesh_cfg.scale_factor,
    }

    if config.wet_mode.enabled:
        from eigenfrequencies.added_mass.core import compare

        metadata["wet_mode"] = compare(frequencies, config.wet_mode)

    return ModalResult(
        frequencies_hz=tuple(float(f) for f in frequencies),
        resonance_penalty=float(penalty),
        violating_modes=tuple(int(i) for i in violators),
        band_report=report,
        metadata=metadata,
    )


def solve_modal_penalty(
    msh_path: Union[str, Path],
    config: ModalAnalysisConfig,
) -> float:
    """Convenience wrapper returning only the raw resonance penalty."""
    return solve_modal(msh_path, config).resonance_penalty


def load_preset(
    machine: str,
    overrides: Optional[Mapping[str, Any]] = None,
) -> ModalAnalysisConfig:
    """Build a ``ModalAnalysisConfig`` from a machine preset + targeted overrides.

    ``overrides`` may contain ``n_rpm`` (handled separately) plus any
    ``ResonanceConfig`` field (``Z_guidevanes``, ``max_harmonic``, ``margin_hz``,
    ``margin_fraction``, ``penalty_k``).
    """
    from eigenfrequencies.machines import load_machine

    preset = load_machine(machine)
    values = dict(overrides or {})
    n_rpm = values.pop("n_rpm", None)
    if n_rpm is None:
        raise ValueError("load_preset overrides must include 'n_rpm'")

    resonance = ResonanceConfig(n_rpm=float(n_rpm), **{**preset.resonance, **values})
    return ModalAnalysisConfig(
        resonance=resonance,
        material=preset.material,
        bc=preset.bc,
        mesh=preset.mesh,
        solver=preset.solver,
    )
