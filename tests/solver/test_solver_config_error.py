"""Test that invalid solver configurations raise SolverConfigError."""

import numpy as np
import pytest

from eigenfrequencies.config import BCConfig, MaterialConfig, SolverConfig
from eigenfrequencies.solver import ModalSolver, SolverConfigError


def _dummy_domain():
    """Return a minimal mesh for config-error tests (no real solve)."""
    from dolfinx import mesh
    from mpi4py import MPI

    domain = mesh.create_unit_cube(MPI.COMM_WORLD, 2, 2, 2, mesh.CellType.tetrahedron)
    return domain


@pytest.mark.requires_container
def test_unknown_backend_raises():
    """An unsupported solver_backend string raises SolverConfigError."""
    domain = _dummy_domain()
    material = MaterialConfig()
    bc_config = BCConfig(mode="free")
    solver_config = SolverConfig(solver_backend="unknown_backend")

    solver = ModalSolver(domain, material, bc_config, solver_config)
    with pytest.raises(SolverConfigError) as exc_info:
        solver.solve()
    assert "solver_backend" in str(exc_info.value)


@pytest.mark.requires_container
def test_slepc_accepts_a_clamped_bc():
    """SLEPc solves the clamped problem — it used to reject it outright.

    The clamp is imposed by assembly (unit diagonal in K, zero in M), not by
    removing DOFs, so the constrained rows sit at an infinite eigenvalue and
    drop out of the spectrum. What is checked here is only that the path runs
    and produces physical frequencies; that it produces the *right* ones is
    ``test_backends_agree_on_the_clamped_problem``.
    """
    domain = _dummy_domain()
    bc_config = BCConfig(mode="axial_plane", axis="x", plane_value=0.0)
    solver_config = SolverConfig(
        solver_backend="slepc", num_eigenvalues=3, element_degree=1
    )

    solver = ModalSolver(domain, MaterialConfig(), bc_config, solver_config)
    eigenvalues, _ = solver.solve()
    frequencies = solver.compute_frequencies(eigenvalues)

    assert solver.backend_used == "slepc"
    assert len(frequencies) >= 1
    # A clamped body has no rigid-body modes, and no spurious mode from the
    # constrained rows survived into the result.
    assert np.all(frequencies > 1.0)
    assert np.all(np.isfinite(frequencies))


@pytest.mark.requires_container
def test_invalid_bc_mode_raises():
    """An invalid BCConfig.mode raises SolverConfigError during solve."""
    domain = _dummy_domain()
    material = MaterialConfig()
    bc_config = BCConfig(mode="unsupported_mode")
    solver_config = SolverConfig(solver_backend="scipy")

    solver = ModalSolver(domain, material, bc_config, solver_config)
    with pytest.raises(SolverConfigError) as exc_info:
        solver.solve()
    assert "mode" in str(exc_info.value).lower()
