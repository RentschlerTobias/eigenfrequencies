"""Characterization test: solver golden references.

Verifies that the modal solver produces stable eigenfrequencies and mode shapes
against frozen golden JSON files.  The test regenerates the solution on-the-fly
with the current code and compares against the stored reference.

Imports ONLY from the eigenfrequencies package (no demo/beam or turbine_runner
path hacks).  The beam mesh is generated inline with gmsh so the test is fully
self-contained.
"""

import json
import os
import tempfile

import numpy as np
import pytest

from eigenfrequencies.config import (
    BCConfig,
    MaterialConfig,
    MeshConfig,
    SolverConfig,
)
from eigenfrequencies.io import load_and_prepare_mesh
from eigenfrequencies.solver import ModalSolver

_REPO_ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
_GOLDEN_DIR = os.path.join(os.path.dirname(__file__), "golden")
_BEAM_GOLDEN = os.path.join(_GOLDEN_DIR, "beam.json")
_TESTCASE_GOLDEN = os.path.join(_GOLDEN_DIR, "testcase_coarse.json")

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


def _generate_beam_msh(output_dir: str, length=1.0, width=0.1, height=0.01, lc=0.1) -> str:
    """Generate a rectangular beam mesh with gmsh (inline, no demo/beam import)."""
    import gmsh

    gmsh.initialize()
    gmsh.option.setNumber("Mesh.Algorithm", 6)
    gmsh.model.add("beam")

    L, B, H = length, width, height
    B2 = B / 2
    H2 = H / 2

    occ = gmsh.model.occ
    p1 = occ.addPoint(0, -B2, -H2, lc)
    p2 = occ.addPoint(L, -B2, -H2, lc)
    p3 = occ.addPoint(L, B2, -H2, lc)
    p4 = occ.addPoint(0, B2, -H2, lc)
    p5 = occ.addPoint(0, -B2, H2, lc)
    p6 = occ.addPoint(L, -B2, H2, lc)
    p7 = occ.addPoint(L, B2, H2, lc)
    p8 = occ.addPoint(0, B2, H2, lc)

    e1 = occ.addLine(p1, p2)
    e2 = occ.addLine(p2, p3)
    e3 = occ.addLine(p3, p4)
    e4 = occ.addLine(p4, p1)
    e5 = occ.addLine(p5, p6)
    e6 = occ.addLine(p6, p7)
    e7 = occ.addLine(p7, p8)
    e8 = occ.addLine(p8, p5)
    e9 = occ.addLine(p1, p5)
    e10 = occ.addLine(p2, p6)
    e11 = occ.addLine(p3, p7)
    e12 = occ.addLine(p4, p8)

    bottom_loop = occ.addCurveLoop([e1, e2, e3, e4])
    bottom = occ.addSurfaceFilling(bottom_loop)
    top_loop = occ.addCurveLoop([e5, e6, e7, e8])
    top = occ.addSurfaceFilling(top_loop)
    front_loop = occ.addCurveLoop([e1, e10, e5, e9])
    front = occ.addSurfaceFilling(front_loop)
    back_loop = occ.addCurveLoop([e3, e11, e7, e12])
    back = occ.addSurfaceFilling(back_loop)
    left_loop = occ.addCurveLoop([e4, e12, e8, e9])
    left = occ.addSurfaceFilling(left_loop)
    right_loop = occ.addCurveLoop([e2, e10, e6, e11])
    right = occ.addSurfaceFilling(right_loop)

    surfaces = [bottom, top, front, back, left, right]
    surface_loop = occ.addSurfaceLoop(surfaces)
    volume_tag = occ.addVolume([surface_loop])
    occ.synchronize()

    gmsh.model.addPhysicalGroup(3, [volume_tag])
    gmsh.model.setPhysicalName(3, volume_tag, "Beam")
    gmsh.model.occ.synchronize()
    gmsh.model.mesh.generate(3)

    msh_path = os.path.join(output_dir, "beam.msh")
    gmsh.write(msh_path)
    gmsh.finalize()
    return msh_path


@pytest.mark.requires_container
@pytest.mark.slow
def test_beam_golden():
    """Cantilever beam modal solver matches frozen golden reference."""
    golden = _load_golden(_BEAM_GOLDEN)

    output_dir = tempfile.mkdtemp(prefix="beam_test_")
    mesh_file = _generate_beam_msh(
        output_dir,
        length=1.0,
        width=0.1,
        height=0.01,
        lc=0.1,
    )

    from dolfinx.io import gmsh as dgmsh
    from mpi4py import MPI

    mesh_data = dgmsh.read_from_msh(mesh_file, MPI.COMM_WORLD, rank=0, gdim=3)
    domain = mesh_data.mesh

    material = MaterialConfig(
        youngs_modulus=210e9,
        density=7850.0,
        poisson_ratio=0.0,
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

    golden_shapes = golden["mode_shapes"]
    assert len(mode_shapes) == len(golden_shapes), (
        f"Mode-shape count mismatch: got {len(mode_shapes)}, expected {len(golden_shapes)}"
    )

    for i, (computed, expected) in enumerate(zip(mode_shapes, golden_shapes)):
        mac = _compute_mac(computed, expected)
        assert mac >= _MAC_MIN, (
            f"Beam mode {i+1} MAC too low: mac={mac:.6f} (min {_MAC_MIN})"
        )


@pytest.mark.requires_container
@pytest.mark.slow
def test_testcase_coarse_golden():
    """Laval disc coarse mesh (free-free) matches frozen golden reference."""
    golden = _load_golden(_TESTCASE_GOLDEN)

    element_degree = 1
    solver_backend = "scipy"
    num_eigenvalues = 16

    material = MaterialConfig(
        youngs_modulus=75.854e9,
        density=8910.0,
        poisson_ratio=0.34,
    )
    bc_config = BCConfig(mode="free")

    msh_path = os.path.join(_REPO_ROOT, "turbine_runner", "data", "testcase_coarse.msh")
    if not os.path.isfile(msh_path):
        pytest.skip(f"Coarse mesh not found at {msh_path} — generate it first")

    mesh_config = MeshConfig(msh_path=msh_path)
    solver_config = SolverConfig(
        num_eigenvalues=num_eigenvalues,
        tolerance=1e-6,
        element_degree=element_degree,
        solver_backend=solver_backend,
    )

    domain = load_and_prepare_mesh(mesh_config)
    solver = ModalSolver(domain, material, bc_config, solver_config)
    eigenvalues, eigenvectors = solver.solve()
    frequencies = solver.compute_frequencies(eigenvalues)

    rigid_threshold_hz = 1.0
    keep = [i for i, f in enumerate(frequencies) if f >= rigid_threshold_hz]
    elastic_frequencies = [float(frequencies[i]) for i in keep]
    elastic_eigenvectors = [eigenvectors[i] for i in keep]

    first_10_freqs = elastic_frequencies[:10]
    first_10_vectors = elastic_eigenvectors[:10]

    mode_shapes = _extract_mode_shape_norms(first_10_vectors, domain.geometry.x)

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

    golden_shapes = golden["mode_shapes"]
    assert len(mode_shapes) == len(golden_shapes), (
        f"Mode-shape count mismatch: got {len(mode_shapes)}, expected {len(golden_shapes)}"
    )

    for i, (computed, expected) in enumerate(zip(mode_shapes, golden_shapes)):
        mac = _compute_mac(computed, expected)
        assert mac >= _MAC_MIN, (
            f"Testcase mode {i+1} MAC too low: mac={mac:.6f} (min {_MAC_MIN})"
        )
