"""Test SLEPc backend against golden references (free-free).

Skips gracefully when SLEPc is not installed.
"""

import json
import os
import sys

import numpy as np
import pytest

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------
_REPO_ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
_TURBINE_DIR = os.path.join(_REPO_ROOT, "turbine_runner")
_GOLDEN_DIR = os.path.join(os.path.dirname(__file__), "..", "characterization", "golden")
_TESTCASE_GOLDEN = os.path.join(_GOLDEN_DIR, "testcase_coarse.json")

# ---------------------------------------------------------------------------
# Tolerances
# ---------------------------------------------------------------------------
_FREQ_REL_TOL = 1e-4
_MAC_MIN = 0.999


# ---------------------------------------------------------------------------
# Helpers (mirrored from test_golden_solver.py)
# ---------------------------------------------------------------------------
def _extract_mode_shape_norms(eigenvectors, mesh_coords):
    """Return displacement-norm vector per mode for MAC computation."""
    num_nodes = len(mesh_coords)
    norms = []
    for ev in eigenvectors:
        if len(ev) >= num_nodes * 3:
            u = ev[: num_nodes * 3].reshape((num_nodes, 3))
        else:
            u = ev.reshape((-1, 3))
        disp_norm = np.linalg.norm(u, axis=1)
        norms.append(disp_norm)
    return norms


def _compute_mac(mode_a, mode_b):
    """Modal Assurance Criterion between two mode-shape vectors."""
    a = np.asarray(mode_a)
    b = np.asarray(mode_b)
    num = np.abs(np.dot(a, b)) ** 2
    denom = np.dot(a, a) * np.dot(b, b)
    if denom == 0:
        return 0.0
    return float(num / denom)


def _load_golden(path):
    with open(path) as fh:
        return json.load(fh)


# ---------------------------------------------------------------------------
# SLEPc availability check
# ---------------------------------------------------------------------------
slepc_available = False
try:
    import petsc4py  # noqa: F401
    import slepc4py  # noqa: F401

    slepc_available = True
except ImportError:
    pass


# ---------------------------------------------------------------------------
# Testcase coarse (free-free) via SLEPc
# ---------------------------------------------------------------------------
@pytest.mark.skipif(not slepc_available, reason="SLEPc not available")
@pytest.mark.requires_container
@pytest.mark.slow
def test_testcase_free_free_slepc():
    """Laval disc coarse mesh (free-free) via SLEPc matches frozen golden reference."""
    golden = _load_golden(_TESTCASE_GOLDEN)

    # Coarse mesh settings (must match the golden generator)
    element_size = 0.01
    element_degree = 1
    num_eigenvalues = 16

    from eigenfrequencies.config import BCConfig, MaterialConfig, MeshConfig, SolverConfig
    from eigenfrequencies.io import load_and_prepare_mesh
    from eigenfrequencies.solver import ModalSolver

    material = MaterialConfig(
        youngs_modulus=75.854e9,
        density=8910.0,
        poisson_ratio=0.34,
    )
    bc_config = BCConfig(mode="free")

    _REPO_ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
    msh_path = os.path.join(_REPO_ROOT, "turbine_runner", "data", "testcase_coarse.msh")
    mesh_config = MeshConfig(msh_path=msh_path)
    solver_config = SolverConfig(
        num_eigenvalues=num_eigenvalues,
        tolerance=1e-6,
        element_degree=element_degree,
        solver_backend="slepc",
    )

    from eigenfrequencies.io import DEFAULT_STL, stl_to_volume_msh

    if not os.path.isfile(msh_path):
        stl_path = DEFAULT_STL
        stl_to_volume_msh(stl_path, msh_path, element_size=element_size, order=element_degree)

    domain = load_and_prepare_mesh(mesh_config)
    solver = ModalSolver(domain, material, bc_config, solver_config)
    eigenvalues, eigenvectors = solver.solve()
    frequencies = solver.compute_frequencies(eigenvalues)

    # For free-free, remove rigid-body modes (freq < 1 Hz threshold)
    rigid_threshold_hz = 1.0
    keep = [i for i, f in enumerate(frequencies) if f >= rigid_threshold_hz]
    elastic_frequencies = [float(frequencies[i]) for i in keep]
    elastic_eigenvectors = [eigenvectors[i] for i in keep]

    # Take first 10 elastic modes
    first_10_freqs = elastic_frequencies[:10]
    first_10_vectors = elastic_eigenvectors[:10]

    # Extract mode-shape displacement norms
    mode_shapes = _extract_mode_shape_norms(first_10_vectors, domain.geometry.x)

    # Compare frequencies
    golden_freqs = golden["frequencies"]
    assert len(first_10_freqs) == len(golden_freqs), (
        f"Frequency count mismatch: got {len(first_10_freqs)}, expected {len(golden_freqs)}"
    )

    for i, (computed, expected) in enumerate(zip(first_10_freqs, golden_freqs)):
        rel_err = abs(computed - expected) / abs(expected) if expected != 0 else abs(computed)
        assert rel_err <= _FREQ_REL_TOL, (
            f"Testcase mode {i+1} frequency drift: computed={computed:.6f} Hz, "
            f"expected={expected:.6f} Hz, rel_err={rel_err:.6e}"
        )

    # Compare mode shapes via MAC
    golden_shapes = golden["mode_shapes"]
    assert len(mode_shapes) == len(golden_shapes), (
        f"Mode-shape count mismatch: got {len(mode_shapes)}, expected {len(golden_shapes)}"
    )

    for i, (computed, expected) in enumerate(zip(mode_shapes, golden_shapes)):
        mac = _compute_mac(computed, expected)
        assert mac >= _MAC_MIN, (
            f"Testcase mode {i+1} MAC too low: mac={mac:.6f} (min {_MAC_MIN})"
        )
