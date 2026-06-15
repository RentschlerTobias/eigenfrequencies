"""STAGE 2: compute turbine runner eigenfrequencies from a dtOO mesh.

Wires mesh_prep -> RunnerModalSolver -> report. Runs in the fenicsx container.
Before trusting the result, set BCConfig from the axis-discovery diagnostic
(``python3 mesh_prep.py``); see README.
"""

import json
import os

from config import MaterialConfig, BCConfig, MeshConfig, SolverConfig, OutputConfig
from mesh_prep import load_and_prepare_mesh
from solver import RunnerModalSolver


def main() -> None:
    material = MaterialConfig()
    bc_config = BCConfig()
    mesh_config = MeshConfig()
    solver_config = SolverConfig(num_eigenvalues=10, tolerance=1e-6)
    output_config = OutputConfig()

    print("=" * 60)
    print("Turbine Runner Modal Analysis (dtOO -> FEniCSx)")
    print("=" * 60)
    print(f"Mesh:     {mesh_config.msh_path}")
    print(f"Material: E={material.youngs_modulus:.2e} Pa, "
          f"rho={material.density} kg/m^3, nu={material.poisson_ratio}")
    print(f"Clamp:    axis={bc_config.axis}, mode={bc_config.mode}, "
          f"hub_radius={bc_config.hub_radius}")
    print()

    print("Loading and preparing mesh...")
    domain = load_and_prepare_mesh(mesh_config)

    print("Solving modal analysis...")
    solver = RunnerModalSolver(domain, material, bc_config, solver_config)
    eigenvalues, eigenvectors = solver.solve()
    frequencies = solver.compute_frequencies(eigenvalues)

    print()
    print("Computed Eigenfrequencies:")
    print("-" * 40)
    for i, freq in enumerate(frequencies):
        print(f"  Mode {i + 1}: {freq:.2f} Hz")

    os.makedirs(output_config.output_dir, exist_ok=True)
    json_path = os.path.join(output_config.output_dir, output_config.results_json)
    with open(json_path, "w") as fh:
        json.dump(
            {"frequencies_hz": [float(f) for f in frequencies],
             "eigenvalues": [float(ev) for ev in eigenvalues]},
            fh, indent=2,
        )
    print(f"\nFrequencies written to: {json_path}")

    if output_config.save_xdmf:
        _write_results(solver, frequencies, eigenvectors, output_config)

    print("=" * 60)
    print("Done")


def _write_results(solver, frequencies, eigenvectors, output_config) -> None:
    """Write mesh + mode shapes to XDMF and VTK for ParaView inspection.

    Both formats need the output Function degree to match the mesh geometry
    degree. The dtOO mesh is second-order (tet10) while displacement is solved
    on a lower degree, so each mode is interpolated onto a matching-degree space.
    Written here (not via src/io.write_results_xdmf, which references a
    non-existent mesh.function_space).
    """
    from dolfinx import fem
    from dolfinx.io import XDMFFile, VTKFile

    geom_degree = solver.domain.geometry.cmap.degree
    V_out = fem.functionspace(solver.domain, ("Lagrange", geom_degree, (3,)))

    # Pre-build the matching-degree mode functions once, reuse for both writers.
    modes = []
    for i, (freq, vec) in enumerate(zip(frequencies, eigenvectors)):
        u = fem.Function(solver.V)
        u.x.array[:] = vec
        u_out = fem.Function(V_out)
        u_out.interpolate(u)
        u_out.name = f"mode_{i + 1}_{freq:.1f}Hz"
        modes.append(u_out)

    xdmf_path = os.path.join(output_config.output_dir, "modes.xdmf")
    with XDMFFile(solver.domain.comm, xdmf_path, "w") as xdmf:
        xdmf.write_mesh(solver.domain)
        for i, u_out in enumerate(modes):
            xdmf.write_function(u_out, float(i))
    print(f"Mode shapes written to: {xdmf_path}")

    # VTK: geometry-only file (for quick shape inspection) + mode-shape series.
    geom_pvd = os.path.join(output_config.output_dir, "geometry.pvd")
    with VTKFile(solver.domain.comm, geom_pvd, "w") as vtk:
        vtk.write_mesh(solver.domain)
    print(f"Geometry written to: {geom_pvd}")

    modes_pvd = os.path.join(output_config.output_dir, "modes.pvd")
    with VTKFile(solver.domain.comm, modes_pvd, "w") as vtk:
        for i, u_out in enumerate(modes):
            vtk.write_function(u_out, float(i))
    print(f"Mode shapes (VTK) written to: {modes_pvd}")
    print(f"Mode shapes written to: {xdmf_path}")


if __name__ == "__main__":
    main()
