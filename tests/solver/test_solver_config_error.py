"""Test that invalid solver configurations raise SolverConfigError."""

import numpy as np
import pytest

from eigenfrequencies.config import MaterialConfig, BCConfig, SolverConfig
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
def test_slepc_with_clamped_bc_raises():
    """SLEPc backend with a clamped BC raises SolverConfigError."""
    domain = _dummy_domain()
    material = MaterialConfig()
    bc_config = BCConfig(mode="axial_plane", axis="x", plane_value=0.0)
    solver_config = SolverConfig(solver_backend="slepc")

    solver = ModalSolver(domain, material, bc_config, solver_config)
    with pytest.raises(SolverConfigError) as exc_info:
        solver.solve()
    assert "slepc" in str(exc_info.value).lower()
    assert "free" in str(exc_info.value).lower()


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
