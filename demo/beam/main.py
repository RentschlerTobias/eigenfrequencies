"""Main entry point for beam modal analysis demo."""

from solver import ModalSolver
from geometry import generate_mesh
from config import BeamConfig, SolverConfig, OutputConfig
from euler_analytical import analytical_frequencies_cantilever
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def main():
    """Run the beam modal analysis demo."""
    beam_config = BeamConfig(
        length=1.0,
        width=0.1,
        height=0.1,
        youngs_modulus=210e9,
        density=7850.0,
        mesh_resolution=0.1,
    )

    solver_config = SolverConfig(
        freq_min=0.0,
        freq_max=1000.0,
        num_eigenvalues=6,
        tolerance=1e-6,
    )

    output_config = OutputConfig(
        save_vtk=True,
        save_xdmf=True,
    )

    print("=" * 60)
    print("Beam Modal Analysis Demo")
    print("=" * 60)
    print(f"Beam dimensions: {beam_config.length} x {
          beam_config.width} x {beam_config.height} m")
    print(f"Material: E={beam_config.youngs_modulus:.2e} Pa, rho={
          beam_config.density} kg/m³")
    print(f"Boundary condition: cantilever (fixed at x=0)")
    print()

    print("Generating mesh...")
    os.makedirs(output_config.output_dir, exist_ok=True)
    mesh_file = generate_mesh(beam_config, output_config.output_dir)
    print(f"Mesh saved to: {mesh_file}")
    print()

    print("Solving modal analysis...")
    solver = ModalSolver(beam_config, solver_config, output_config, boundary_type="cantilever")
    eigenvalues, _ = solver.solve()

    if eigenvalues is not None and len(eigenvalues) > 0:
        frequencies = solver.compute_frequencies(eigenvalues)
        print()
        print("Computed Eigenfrequencies:")
        print("-" * 40)
        for i, freq in enumerate(frequencies):
            print(f"  Mode {i+1}: {freq:.2f} Hz")
    else:
        print("No eigenvalues converged.")

    print()
    print("Analytical Solution (Euler-Bernoulli - Cantilever):")
    print("-" * 40)
    analytical = analytical_frequencies_cantilever(
        beam_config, solver_config.num_eigenvalues)
    for i, freq in enumerate(analytical):
        print(f"  Mode {i+1}: {freq:.2f} Hz")

    print()
    print("=" * 60)
    print("Done")


if __name__ == "__main__":
    main()
