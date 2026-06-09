"""Cantilever beam validation test.

Compares 3D FEM eigenfrequencies with analytical Euler-Bernoulli solutions
for a cantilever beam (one end clamped at x=0, other end free).
"""

import os
import sys
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from solver import ModalSolver
from geometry import generate_mesh
from config import BeamConfig, SolverConfig, OutputConfig
from cantilever_analytical import analytical_frequencies_cantilever


def classify_mode(eigenvector, mesh_coords):
    """Classify vibration mode based on displacement pattern.
    
    Args:
        eigenvector: Eigenvector array (num_dofs)
        mesh_coords: Node coordinates (num_nodes, 3)
        
    Returns:
        dict with mode classification
    """
    num_nodes = len(mesh_coords)
    
    # For Lagrange-2 elements, the eigenvector has more DOFs than nodes
    # We need to evaluate the function at the nodes
    # The DOFs are organized in blocks of 3 (x, y, z components)
    # For nodes, we can just take the first DOF for each component at each node
    # This is an approximation but works for classification
    
    # Extract the displacement values for each node
    # The eigenvector contains values for all DOFs, but we need node values
    # For simplicity, we'll take the first 3*num_nodes values (node values)
    # and ignore the edge/face DOFs for classification
    
    if len(eigenvector) >= num_nodes * 3:
        # Take the first 3*num_nodes values (node values for P1 or P2)
        u = eigenvector[:num_nodes * 3].reshape((num_nodes, 3))
    else:
        # If eigenvector is smaller than expected, just reshape what we have
        u = eigenvector.reshape((-1, 3))
    
    # Extract displacement components
    ux = u[:, 0]
    uy = u[:, 1]
    uz = u[:, 2]
    
    # Max absolute displacements
    max_ux = np.max(np.abs(ux))
    max_uy = np.max(np.abs(uy))
    max_uz = np.max(np.abs(uz))
    
    # Determine dominant direction
    displacements = {"x": max_ux, "y": max_uy, "z": max_uz}
    dominant = max(displacements, key=displacements.get)
    
    # Check for torsion (rotation about x-axis)
    # Torsion: top and bottom nodes move in opposite z-directions
    y_coords = mesh_coords[:, 1]
    z_coords = mesh_coords[:, 2]
    
    top_mask = z_coords > 0
    bottom_mask = z_coords < 0
    
    if np.any(top_mask) and np.any(bottom_mask):
        uy_top = uy[top_mask]
        uy_bottom = uy[bottom_mask]
        uz_top = uz[top_mask]
        uz_bottom = uz[bottom_mask]
        
        # Torsion indicator: opposite z-displacement at top vs bottom
        torsion_indicator = np.abs(np.mean(uz_top) - np.mean(uz_bottom))
    else:
        torsion_indicator = 0
    
    # Classify mode
    if torsion_indicator > 0.5 * max_uz:
        mode_type = "torsion"
    elif dominant == "x":
        mode_type = "axial"
    elif dominant == "y":
        mode_type = "bending_y"
    elif dominant == "z":
        mode_type = "bending_z"
    else:
        mode_type = "unknown"
    
    return {
        "type": mode_type,
        "dominant": dominant,
        "max_ux": max_ux,
        "max_uy": max_uy,
        "max_uz": max_uz,
        "torsion_indicator": torsion_indicator,
    }


def plot_mode_shape(eigenvector, mesh_coords, mode_num, output_dir):
    """Plot mode shape using matplotlib.
    
    Creates a 2D projection showing the undeformed and deformed beam.
    """
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
    except ImportError:
        print("matplotlib not available, skipping plots")
        return
    
    num_nodes = len(mesh_coords)
    
    # For Lagrange-2 elements, the eigenvector has more DOFs than nodes
    # Extract the first 3*num_nodes values for node-based visualization
    if len(eigenvector) >= num_nodes * 3:
        u = eigenvector[:num_nodes * 3].reshape((num_nodes, 3))
    else:
        u = eigenvector.reshape((-1, 3))
    
    # Scale displacement for visualization
    max_disp = np.max(np.abs(u))
    if max_disp > 0:
        scale = 0.2 * np.max(mesh_coords[:, 0]) / max_disp  # Scale to 20% of beam length
    else:
        scale = 1.0
    
    # Deformed coordinates
    deformed = mesh_coords + scale * u
    
    fig, axes = plt.subplots(1, 2, figsize=(12, 5))
    
    # Side view (x-y plane)
    ax1 = axes[0]
    ax1.plot(mesh_coords[:, 0], mesh_coords[:, 1], 'b.', alpha=0.3, label='undeformed')
    ax1.plot(deformed[:, 0], deformed[:, 1], 'r.', alpha=0.5, label='deformed')
    ax1.set_xlabel('x [m]')
    ax1.set_ylabel('y [m]')
    ax1.set_title(f'Mode {mode_num}: Side view (x-y)')
    ax1.legend()
    ax1.grid(True)
    ax1.axis('equal')
    
    # Top view (x-z plane)
    ax2 = axes[1]
    ax2.plot(mesh_coords[:, 0], mesh_coords[:, 2], 'b.', alpha=0.3, label='undeformed')
    ax2.plot(deformed[:, 0], deformed[:, 2], 'r.', alpha=0.5, label='deformed')
    ax2.set_xlabel('x [m]')
    ax2.set_ylabel('z [m]')
    ax2.set_title(f'Mode {mode_num}: Top view (x-z)')
    ax2.legend()
    ax2.grid(True)
    ax2.axis('equal')
    
    plt.tight_layout()
    plot_file = os.path.join(output_dir, f"mode_{mode_num}_shape.png")
    plt.savefig(plot_file, dpi=150)
    plt.close()
    print(f"  Mode shape plot saved to: {plot_file}")


def main():
    """Run cantilever beam validation test."""
    beam_config = BeamConfig(
        length=1.0,
        width=0.01,
        height=0.1,
        youngs_modulus=210e9,
        density=7850.0,
        mesh_resolution=0.1,
    )
    
    solver_config = SolverConfig(
        freq_min=0.0,
        freq_max=1000.0,
        num_eigenvalues=12,
        tolerance=1e-6,
    )
    
    output_config = OutputConfig(
        save_vtk=True,
        save_xdmf=True,
    )
    
    print("=" * 70)
    print("Cantilever Beam Validation Test")
    print("=" * 70)
    print(f"Beam dimensions: {beam_config.length} x {beam_config.width} x {beam_config.height} m")
    print(f"Material: E={beam_config.youngs_modulus:.2e} Pa, rho={beam_config.density} kg/m³")
    print(f"Mesh resolution: {beam_config.mesh_resolution} m")
    print()
    
    # Analytical solution
    print("Analytical Solution (Cantilever - Euler-Bernoulli):")
    print("-" * 50)
    analytical_freqs = analytical_frequencies_cantilever(beam_config, solver_config.num_eigenvalues)
    for i, freq in enumerate(analytical_freqs):
        print(f"  Mode {i+1}: {freq:.4f} Hz")
    print()
    
    # Generate mesh
    print("Generating mesh...")
    os.makedirs(output_config.output_dir, exist_ok=True)
    mesh_file = generate_mesh(beam_config, output_config.output_dir)
    print(f"Mesh saved to: {mesh_file}")
    print()
    
    # Solve 3D FEM
    print("Solving 3D FEM modal analysis...")
    solver = ModalSolver(beam_config, solver_config, output_config, boundary_type="cantilever")
    eigenvalues, eigenvectors = solver.solve()
    
    if eigenvalues is None or len(eigenvalues) == 0:
        print("No eigenvalues converged!")
        return
    
    frequencies = solver.compute_frequencies(eigenvalues)
    
    # Get mesh coordinates for mode analysis
    domain = solver.create_mesh()
    mesh_coords = domain.geometry.x
    
    print()
    print("3D FEM Results:")
    print("-" * 50)
    
    # Analyze and classify modes
    mode_info = []
    for i, (freq, ev) in enumerate(zip(frequencies, eigenvectors)):
        info = classify_mode(ev, mesh_coords)
        info["fem_freq"] = freq
        info["mode_num"] = i + 1
        mode_info.append(info)
        
        print(f"  Mode {i+1}: {freq:.4f} Hz  ({info['type']}, dominant: {info['dominant']})")
    
    print()
    
    # Extract bending modes in z-direction (primary bending direction for analytical comparison)
    bending_z_modes = [m for m in mode_info if m["type"] == "bending_z"]
    
    print("=" * 70)
    print("Comparison: Bending Modes (z-direction)")
    print("=" * 70)
    print(f"{'Mode':<6} {'Analytical':<15} {'3D FEM':<15} {'Error %':<12} {'Status'}")
    print("-" * 70)
    
    num_compare = min(len(analytical_freqs), len(bending_z_modes))
    for i in range(num_compare):
        analytical_freq = analytical_freqs[i]
        fem_mode = bending_z_modes[i]
        fem_freq = fem_mode["fem_freq"]
        error_percent = abs(fem_freq - analytical_freq) / analytical_freq * 100
        
        status = "✓ PASS" if error_percent < 5.0 else "✗ FAIL"
        
        print(f"{i+1:<6} {analytical_freq:<15.4f} {fem_freq:<15.4f} {error_percent:<12.2f} {status}")
    
    print()
    
    # Also show bending modes in y-direction
    bending_y_modes = [m for m in mode_info if m["type"] == "bending_y"]
    
    print("=" * 70)
    print("Bending Modes (y-direction) - Lower stiffness due to smaller I_z")
    print("=" * 70)
    print(f"{'Mode':<6} {'3D FEM':<15} {'Type':<20}")
    print("-" * 70)
    
    for i, fem_mode in enumerate(bending_y_modes):
        fem_freq = fem_mode["fem_freq"]
        print(f"{i+1:<6} {fem_freq:<15.4f} {fem_mode['type']:<20}")
    
    print()
    
    # Plot mode shapes
    print("Generating mode shape plots...")
    for i, (freq, ev) in enumerate(zip(frequencies, eigenvectors)):
        plot_mode_shape(ev, mesh_coords, i+1, output_config.output_dir)
    
    print()
    print("=" * 70)
    print("Done")
    print("=" * 70)


if __name__ == "__main__":
    main()
