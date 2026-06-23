"""Spline Beam Optimization Demo

Optimizes a 3-point spline beam to avoid a forbidden frequency interval.

Usage:
    python beam_spline_optimization.py
"""

import os
import numpy as np

from config import BeamConfig, SolverConfig, OptimizationConfig, OutputConfig
from optimization import optimize_spline_beam, plot_spline_shape


def main():
    """Run spline beam optimization demo."""
    
    # Configuration
    beam_config = BeamConfig(
        length=1.0,
        width=0.1,
        height=0.01,
        youngs_modulus=210e9,
        density=7850.0,
        mesh_resolution=0.1,
    )
    
    solver_config = SolverConfig(
        num_eigenvalues=10,
        tolerance=1e-3,
    )
    
    # Optimization: avoid frequencies in [0, 50] Hz
    opt_config = OptimizationConfig(
        f_min=0.0,
        f_max=50.0,
        penalty_k=1e6,
        max_iter=50,
    )
    
    output_config = OutputConfig(
        output_dir=os.path.join(os.path.dirname(__file__), "output"),
    )
    
    # Initial design
    x0 = np.array([0.5, 0.0, 0.0])
    
    # Bounds: [x1_fraction, y1, y2]
    # x1 is fraction of beam length (0.1 to 0.9)
    # y1, y2 are lateral deviations
    bounds = np.array([
        [0.1, 0.9],  # x1 fraction
        [-0.1, 0.1],  # y1 (meters)
        [-0.1, 0.1],  # y2 (meters)
    ])
    
    # Run optimization
    result = optimize_spline_beam(
        beam_config=beam_config,
        solver_config=solver_config,
        opt_config=opt_config,
        output_config=output_config,
        x0=x0,
        bounds=bounds,
        method="Nelder-Mead",
    )
    
    # Plot final spline shape
    plot_spline_shape(beam_config, result['spline_config'])
    
    print("\n=== Optimization Complete ===")
    print(f"Optimal control points:")
    print(f"  x1 = {result['spline_config'].x1:.4f} m")
    print(f"  y1 = {result['spline_config'].y1:.4f} m")
    print(f"  y2 = {result['spline_config'].y2:.4f} m")
    
    return result


if __name__ == "__main__":
    main()
