"""Beam validation test: 3D FEM vs analytical Euler-Bernoulli."""

import os
import sys

import numpy as np
import pytest

from eigenfrequencies.validation.beam.analytical import analytical_frequencies_cantilever
from eigenfrequencies.validation.beam.analytical import classify_mode

TOLERANCE_PCT = 5.0


@pytest.mark.requires_container
@pytest.mark.slow
def test_beam_fem_vs_analytical():
    """Cantilever beam FEM frequencies match analytical within tolerance."""
    pytest.importorskip("dolfinx", reason="fenicsx container only")

    _BEAM_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "demo", "beam")
    sys.path.insert(0, _BEAM_DIR)

    from config import BeamConfig, SolverConfig, OutputConfig
    from geometry import generate_mesh
    from solver import ModalSolver

    beam_config = BeamConfig(
        length=1.0,
        width=0.1,
        height=0.01,
        youngs_modulus=210e9,
        density=7850.0,
        mesh_resolution=0.1,
    )
    solver_config = SolverConfig(
        freq_min=0.0,
        freq_max=1000.0,
        num_eigenvalues=10,
        tolerance=1e-6,
    )
    output_config = OutputConfig(
        save_vtk=False,
        save_xdmf=False,
        output_dir=os.path.join(os.path.dirname(__file__), "output", "beam_validation"),
    )
    os.makedirs(output_config.output_dir, exist_ok=True)

    # Generate mesh
    mesh_file = generate_mesh(beam_config, output_config.output_dir)

    # Solve FEM
    solver = ModalSolver(beam_config, solver_config, output_config, boundary_type="cantilever")
    eigenvalues, eigenvectors = solver.solve()
    assert eigenvalues is not None and len(eigenvalues) > 0, "No eigenvalues converged"
    frequencies = solver.compute_frequencies(eigenvalues)

    # Get mesh coordinates for mode classification
    domain = solver.create_mesh()
    mesh_coords = domain.geometry.x

    # Classify modes and extract bending_z modes
    mode_info = []
    for i, (freq, ev) in enumerate(zip(frequencies, eigenvectors)):
        info = classify_mode(ev, mesh_coords)
        info["fem_freq"] = freq
        info["mode_num"] = i + 1
        mode_info.append(info)

    bending_z_modes = [m for m in mode_info if m["type"] == "bending_z"]

    # Analytical reference (cantilever, bending about y-axis -> displacement in z)
    analytical_freqs = analytical_frequencies_cantilever(
        beam_config, solver_config.num_eigenvalues, axis="y"
    )

    # Compare bending_z modes with analytical
    num_compare = min(len(analytical_freqs), len(bending_z_modes))
    assert num_compare >= 2, f"Expected >= 2 bending_z modes, got {len(bending_z_modes)}"

    for i in range(num_compare):
        fem_freq = bending_z_modes[i]["fem_freq"]
        ana_freq = analytical_freqs[i]
        error_percent = abs(fem_freq - ana_freq) / ana_freq * 100
        assert error_percent < TOLERANCE_PCT, (
            f"Mode {i+1}: FEM={fem_freq:.4f} Hz, "
            f"Analytical={ana_freq:.4f} Hz, "
            f"Error={error_percent:.2f}% (limit {TOLERANCE_PCT}%)"
        )
