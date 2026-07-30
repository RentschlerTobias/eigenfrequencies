"""Test SciPy backend against golden references.

Uses the new generic ModalSolver from eigenfrequencies.solver, injecting
BCConfig so no runner-specific names remain in the package.
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
_BEAM_DIR = os.path.join(_REPO_ROOT, "demo", "beam")
_GOLDEN_DIR = os.path.join(os.path.dirname(__file__), "..", "characterization", "golden")
_BEAM_GOLDEN = os.path.join(_GOLDEN_DIR, "beam.json")

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
# Beam clamped test
# ---------------------------------------------------------------------------
@pytest.mark.requires_container
@pytest.mark.slow
def test_beam_clamped_scipy():
    """Cantilever beam via generic ModalSolver matches frozen golden reference."""
    golden = _load_golden(_BEAM_GOLDEN)

    # Generate beam mesh using demo/beam geometry module
    sys.path.insert(0, _BEAM_DIR)
    try:
        from config import BeamConfig, OutputConfig  # noqa: E402
        from config import SolverConfig as BeamSolverConfig
        from geometry import generate_mesh as beam_generate_mesh  # noqa: E402
    finally:
        sys.path.remove(_BEAM_DIR)
        for _mod_name in list(sys.modules):
            if _mod_name in ("config", "geometry"):
                del sys.modules[_mod_name]

    beam_config = BeamConfig(
        length=1.0,
        width=0.1,
        height=0.01,
        youngs_modulus=210e9,
        density=7850.0,
        mesh_resolution=0.1,
    )
    import tempfile
    output_dir = tempfile.mkdtemp(prefix="beam_test_")
    mesh_file = beam_generate_mesh(beam_config, output_dir)

    # Load mesh with dolfinx
    from dolfinx.io import gmsh
    from mpi4py import MPI

    mesh_data = gmsh.read_from_msh(mesh_file, MPI.COMM_WORLD, rank=0, gdim=3)
    domain = mesh_data.mesh

    # Use the generic ModalSolver with injected BCConfig
    from eigenfrequencies.config import BCConfig, MaterialConfig, SolverConfig
    from eigenfrequencies.solver import ModalSolver

    material = MaterialConfig(
        youngs_modulus=beam_config.youngs_modulus,
        density=beam_config.density,
        poisson_ratio=0.0,  # beam demo uses nu=0 to match Euler-Bernoulli
    )
    bc_config = BCConfig(
        mode="axial_plane",
        axis="x",
        plane_value=0.0,
        plane_tol=1e-6,
    )
    solver_config = SolverConfig(
        num_eigenvalues=10,
        tolerance=1e-6,
        element_degree=2,
        solver_backend="scipy",
    )

    solver = ModalSolver(domain, material, bc_config, solver_config)
    eigenvalues, eigenvectors = solver.solve()
    frequencies = solver.compute_frequencies(eigenvalues)

    mesh_coords = domain.geometry.x
    mode_shapes = _extract_mode_shape_norms(eigenvectors, mesh_coords)

    # Compare frequencies
    golden_freqs = golden["frequencies"]
    assert len(frequencies) == len(golden_freqs), (
        f"Frequency count mismatch: got {len(frequencies)}, expected {len(golden_freqs)}"
    )

    for i, (computed, expected) in enumerate(zip(frequencies, golden_freqs)):
        rel_err = abs(computed - expected) / abs(expected) if expected != 0 else abs(computed)
        assert rel_err <= _FREQ_REL_TOL, (
            f"Beam mode {i+1} frequency drift: computed={computed:.6f} Hz, "
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
            f"Beam mode {i+1} MAC too low: mac={mac:.6f} (min {_MAC_MIN})"
        )
