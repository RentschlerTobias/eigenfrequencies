"""Free-free mode and SLEPc backend tests (run inside the fenicsx container).

Pure-logic tests (backend flag, rigid-mode filtering, label pairing) sit next to
integration tests that build a tiny free-free block mesh and cross-check the
SLEPc backend against the scipy reference on identical physics.

    docker run --rm -i -v "$PWD:/workspace" -w /workspace/turbine_runner \
        eigenfrequencies-fenicsx:latest python3 -m pytest test_free_mode.py -q
"""

import numpy as np
import pytest

from config import MaterialConfig, BCConfig, SolverConfig
from validate_testcase import elastic_modes, assign_mode_labels


def test_solver_backend_defaults_to_scipy():
    assert SolverConfig().solver_backend == "scipy"


def test_solver_backend_accepts_slepc():
    cfg = SolverConfig(solver_backend="slepc", element_degree=2)
    assert cfg.solver_backend == "slepc"
    assert cfg.element_degree == 2


def test_elastic_modes_drops_rigid():
    freqs = np.array([0.001, 0.5, 0.9, 192.8, 299.125, 712.0])
    vecs = [np.full(4, float(i)) for i in range(len(freqs))]
    n_rigid, elastic_f, elastic_v = elastic_modes(freqs, vecs)
    assert n_rigid == 3
    assert elastic_f == [192.8, 299.125, 712.0]
    assert len(elastic_v) == 3


def test_assign_mode_labels_follows_degeneracy():
    elastic_f = [230.0, 232.0, 266.0, 356.0, 357.0]
    labeled = assign_mode_labels(elastic_f)
    assert labeled["1ND"] == [230.0, 232.0]
    assert labeled["Torsion"] == [266.0]
    assert labeled["2ND"] == [356.0, 357.0]


def _tiny_block_solver(backend):
    """Free-free bronze block, coarse enough for both backends to solve."""
    from mpi4py import MPI
    from dolfinx import mesh as dmesh
    from solver import RunnerModalSolver

    domain = dmesh.create_box(
        MPI.COMM_WORLD, [[0.0, 0.0, 0.0], [0.1, 0.05, 0.02]], [5, 3, 2]
    )
    material = MaterialConfig(
        youngs_modulus=75.854e9, density=8910.0, poisson_ratio=0.34
    )
    return RunnerModalSolver(
        domain,
        material,
        BCConfig(mode="free"),
        SolverConfig(num_eigenvalues=9, tolerance=1e-9, solver_backend=backend),
    )


def test_apply_bc_free_returns_no_clamp():
    from dolfinx import fem

    solver = _tiny_block_solver("scipy")
    V = fem.functionspace(solver.domain, ("Lagrange", 1, (3,)))
    bc, dofs = solver.apply_bc(V)
    assert bc is None
    assert dofs.size == 0


def _dense_reference_elastic(domain, material, n_modes=3):
    """Exact eigenfrequencies of the tiny block via dense generalized eigh."""
    import scipy.linalg
    import ufl
    from dolfinx import fem

    V = fem.functionspace(domain, ("Lagrange", 1, (3,)))
    u, v = ufl.TrialFunction(V), ufl.TestFunction(V)
    E, rho, nu = (material.youngs_modulus, material.density,
                  material.poisson_ratio)
    mu = E / (2 * (1 + nu))
    lmbda = E * nu / ((1 + nu) * (1 - 2 * nu))
    eps = lambda w: ufl.sym(ufl.grad(w))
    sig = lambda w: lmbda * ufl.tr(eps(w)) * ufl.Identity(3) + 2 * mu * eps(w)
    a = fem.form(ufl.inner(sig(u), eps(v)) * ufl.dx)
    b = fem.form(rho * ufl.dot(u, v) * ufl.dx)
    K = fem.assemble_matrix(a, bcs=[]).to_scipy().toarray()
    M = fem.assemble_matrix(b, bcs=[]).to_scipy().toarray()
    lam = scipy.linalg.eigh(K, M, subset_by_index=[6, 6 + n_modes - 1])[0]
    return np.sqrt(np.abs(lam)) / (2 * np.pi)


def test_backends_match_dense_reference():
    """Both backends: 6 rigid modes, elastic modes within 0.5% of dense."""
    ref = _tiny_block_solver("scipy")
    dense_f = _dense_reference_elastic(ref.domain, ref.material)

    for backend in ("scipy", "slepc"):
        solver = _tiny_block_solver(backend)
        lam, vecs = solver.solve()
        freqs = solver.compute_frequencies(lam)
        n_rigid, elastic_f, _ = elastic_modes(freqs, vecs)
        assert n_rigid == 6, f"{backend}: expected 6 rigid modes, got {n_rigid}"
        assert getattr(solver, "backend_used", "unset") == backend
        assert len(vecs) == len(lam)
        assert vecs[0].ndim == 1 and vecs[0].size > 0
        np.testing.assert_allclose(
            elastic_f[:3], dense_f, rtol=5e-3,
            err_msg=f"{backend} deviates from dense reference",
        )
