"""Characterization test: solver golden references.

Verifies that the modal solver produces stable eigenfrequencies and mode shapes
against frozen golden JSON files.  The test regenerates the solution on-the-fly
with the current code and compares against the stored reference.

Work-around for the import-time XML read in config.py (Todo 7):
  N_RPM=72 is set in the environment before importing turbine_runner.config.
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
_TURBINE_DIR = os.path.join(_REPO_ROOT, "turbine_runner")

# ---------------------------------------------------------------------------
# Prevent import-time templateState.xml read (known issue, fixed in Todo 7).
# ---------------------------------------------------------------------------
os.environ["N_RPM"] = "72"

# ---------------------------------------------------------------------------
# Imports — beam
# ---------------------------------------------------------------------------
# Temporarily add beam dir to sys.path so that solver.py's internal
# ``from config import …`` resolves to demo/beam/config.py.
sys.path.insert(0, _BEAM_DIR)

import config as _beam_config  # noqa: E402
BeamConfig = _beam_config.BeamConfig
BeamSolverConfig = _beam_config.SolverConfig
BeamOutputConfig = _beam_config.OutputConfig

from solver import ModalSolver  # noqa: E402
from geometry import generate_mesh as beam_generate_mesh  # noqa: E402

# Remove beam modules from sys.modules so turbine imports don't collide.
for _mod_name in list(sys.modules):
    if _mod_name in ("config", "solver", "geometry"):
        del sys.modules[_mod_name]

sys.path.remove(_BEAM_DIR)

# ---------------------------------------------------------------------------
# Imports — turbine_runner
# ---------------------------------------------------------------------------
sys.path.insert(0, _TURBINE_DIR)

import config as _turbine_config  # noqa: E402
MaterialConfig = _turbine_config.MaterialConfig
BCConfig = _turbine_config.BCConfig
MeshConfig = _turbine_config.MeshConfig
RunnerSolverConfig = _turbine_config.SolverConfig

from mesh_prep import load_and_prepare_mesh  # noqa: E402
from solver import RunnerModalSolver  # noqa: E402
from stl_to_msh import stl_to_volume_msh, DEFAULT_STL  # noqa: E402

# ---------------------------------------------------------------------------
# Golden paths
# ---------------------------------------------------------------------------
_GOLDEN_DIR = os.path.join(os.path.dirname(__file__), "golden")
_BEAM_GOLDEN = os.path.join(_GOLDEN_DIR, "beam.json")
_TESTCASE_GOLDEN = os.path.join(_GOLDEN_DIR, "testcase_coarse.json")

# ---------------------------------------------------------------------------
# Tolerances
# ---------------------------------------------------------------------------
_FREQ_REL_TOL = 1e-4
_MAC_MIN = 0.999


def _extract_mode_shape_norms(eigenvectors, mesh_coords):
    """Return displacement-norm vector per mode for MAC computation."""
    num_nodes = len(mesh_coords)
    norms = []
    for ev in eigenvectors:
        if len(ev) >= num_nodes * 3:
            u = ev[:num_nodes * 3].reshape((num_nodes, 3))
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


# ==========================================================================
# Beam
# ==========================================================================

@pytest.mark.requires_container
@pytest.mark.slow
def test_beam_golden():
    """Cantilever beam modal solver matches frozen golden reference."""
    golden = _load_golden(_BEAM_GOLDEN)

    beam_config = BeamConfig(
        length=1.0,
        width=0.1,
        height=0.01,
        youngs_modulus=210e9,
        density=7850.0,
        mesh_resolution=0.1,
    )
    solver_config = BeamSolverConfig(
        freq_min=0.0,
        freq_max=1000.0,
        num_eigenvalues=10,
        tolerance=1e-6,
    )
    output_config = BeamOutputConfig(
        save_vtk=False,
        save_xdmf=False,
        output_dir=os.path.join(os.path.dirname(__file__), "output", "beam_test"),
    )
    os.makedirs(output_config.output_dir, exist_ok=True)

    # Generate mesh
    mesh_file = beam_generate_mesh(beam_config, output_config.output_dir)

    # Solve
    solver = ModalSolver(beam_config, solver_config, output_config, boundary_type="cantilever")
    eigenvalues, eigenvectors = solver.solve()
    frequencies = solver.compute_frequencies(eigenvalues)

    domain = solver.create_mesh()
    mesh_coords = domain.geometry.x

    # Extract mode-shape displacement norms
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


# ==========================================================================
# Testcase coarse (Laval disc, free-free)
# ==========================================================================

@pytest.mark.requires_container
@pytest.mark.slow
def test_testcase_coarse_golden():
    """Laval disc coarse mesh (free-free) matches frozen golden reference."""
    golden = _load_golden(_TESTCASE_GOLDEN)

    # Coarse mesh settings (must match the golden generator)
    element_size = 0.01
    element_degree = 1
    solver_backend = "scipy"
    num_eigenvalues = 16

    material = MaterialConfig(
        youngs_modulus=75.854e9,
        density=8910.0,
        poisson_ratio=0.34,
    )
    bc_config = BCConfig(mode="free")

    msh_path = "/workspace/turbine_runner/data/testcase_coarse.msh"
    mesh_config = MeshConfig(msh_path=msh_path)
    solver_config = RunnerSolverConfig(
        num_eigenvalues=num_eigenvalues,
        tolerance=1e-6,
        element_degree=element_degree,
        solver_backend=solver_backend,
    )

    # Generate coarse mesh if missing
    if not os.path.isfile(msh_path):
        stl_path = DEFAULT_STL
        stl_to_volume_msh(stl_path, msh_path, element_size=element_size, order=element_degree)

    # Solve
    domain = load_and_prepare_mesh(mesh_config)
    solver = RunnerModalSolver(domain, material, bc_config, solver_config)
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
