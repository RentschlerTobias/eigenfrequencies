"""Spline beam optimization for frequency avoidance."""

import numpy as np
from scipy.optimize import minimize
import matplotlib.pyplot as plt

from config import BeamConfig, SplineConfig, SolverConfig, OptimizationConfig, OutputConfig
from geometry_spline import generate_spline_mesh
from solver import ModalSolver


def compute_penalty(frequencies: np.ndarray, opt_config: OptimizationConfig) -> float:
    """Compute penalty for frequencies within forbidden interval.
    
    penalty = sum_i k / (f_i - f_min) if f_i in [f_min, f_max]
    
    Args:
        frequencies: Array of frequencies in Hz
        opt_config: Optimization configuration
        
    Returns:
        Total penalty value
    """
    f_min = opt_config.f_min
    f_max = opt_config.f_max
    k = opt_config.penalty_k
    
    penalty = 0.0
    
    for f in frequencies:
        if f_min < f < f_max:
            # Frequency is in the forbidden interval
            # Penalty is proportional to closeness to bounds
            if f - f_min < f_max - f:
                # Closer to lower bound
                penalty += k / (f - f_min + 1e-6)
            else:
                # Closer to upper bound
                penalty += k / (f_max - f + 1e-6)
    
    return penalty


def evaluate_objective(
    x: np.ndarray,
    beam_config: BeamConfig,
    solver_config: SolverConfig,
    opt_config: OptimizationConfig,
    output_config: OutputConfig,
) -> float:
    """Evaluate objective function for optimization.
    
    Args:
        x: Design variables [x1, y1, y2]
        beam_config: Beam configuration
        solver_config: Solver configuration
        opt_config: Optimization configuration
        output_config: Output configuration
        
    Returns:
        Penalty value
    """
    # Update spline config
    spline_config = SplineConfig(
        x1=x[0],
        y1=x[1],
        y2=x[2],
        num_sections=10,
    )
    
    # Generate mesh
    generate_spline_mesh(beam_config, spline_config, output_config.output_dir)
    
    # Solve
    solver = ModalSolver(beam_config, solver_config, output_config)
    eigenvalues, eigenvectors = solver.solve()
    
    # Compute frequencies
    frequencies = solver.compute_frequencies(eigenvalues)
    
    # Compute penalty
    penalty = compute_penalty(frequencies, opt_config)
    
    return penalty


def optimize_spline_beam(
    beam_config: BeamConfig,
    solver_config: SolverConfig,
    opt_config: OptimizationConfig,
    output_config: OutputConfig,
    x0: np.ndarray = None,
    bounds: np.ndarray = None,
    method: str = "Nelder-Mead",
) -> dict:
    """Optimize spline beam control points to avoid frequency interval.
    
    Args:
        beam_config: Beam configuration
        solver_config: Solver configuration
        opt_config: Optimization configuration
        output_config: Output configuration
        x0: Initial design variables [x1, y1, y2]
        bounds: Variable bounds [(x1_min, x1_max), (y1_min, y1_max), (y2_min, y2_max)]
        method: Optimization method
        
    Returns:
        Optimization result dictionary
    """
    if x0 is None:
        x0 = np.array([0.5, 0.0, 0.0])
    
    if bounds is None:
        # Default bounds
        bounds = np.array([
            [0.1, 0.9],  # x1: fraction of beam length
            [-0.1, 0.1],  # y1: lateral deviation
            [-0.1, 0.1],  # y2: lateral deviation at end
        ])
    
    # Scale bounds to actual beam dimensions
    L = beam_config.length
    bounds_scaled = bounds.copy()
    bounds_scaled[0, :] = bounds[0, :] * L  # x1 scaled by length
    
    # Define objective function
    def objective(x):
        return evaluate_objective(
            x, beam_config, solver_config, opt_config, output_config
        )
    
    print(f"Starting optimization with method={method}")
    print(f"Initial design: x1={x0[0]:.4f}, y1={x0[1]:.4f}, y2={x0[2]:.4f}")
    print(f"Bounds: x1=[{bounds_scaled[0,0]:.4f}, {bounds_scaled[0,1]:.4f}], "
          f"y1=[{bounds_scaled[1,0]:.4f}, {bounds_scaled[1,1]:.4f}], "
          f"y2=[{bounds_scaled[2,0]:.4f}, {bounds_scaled[2,1]:.4f}]")
    
    # Run optimization
    result = minimize(
        objective,
        x0,
        method=method,
        bounds=[tuple(b) for b in bounds_scaled],
        options={'maxiter': opt_config.max_iter, 'disp': True},
    )
    
    # Print results
    print(f"\nOptimization finished!")
    print(f"Success: {result.success}")
    print(f"Final design: x1={result.x[0]:.4f}, y1={result.x[1]:.4f}, y2={result.x[2]:.4f}")
    print(f"Final penalty: {result.fun:.6f}")
    
    # Evaluate final design
    spline_config = SplineConfig(
        x1=result.x[0],
        y1=result.x[1],
        y2=result.x[2],
        num_sections=10,
    )
    
    generate_spline_mesh(beam_config, spline_config, output_config.output_dir)
    solver = ModalSolver(beam_config, solver_config, output_config)
    eigenvalues, eigenvectors = solver.solve()
    frequencies = solver.compute_frequencies(eigenvalues)
    
    print(f"\nFinal frequencies:")
    for i, f in enumerate(frequencies):
        in_interval = opt_config.f_min < f < opt_config.f_max
        marker = " <-- FORBIDDEN" if in_interval else ""
        print(f"  Mode {i+1}: {f:.4f} Hz{marker}")
    
    return {
        'result': result,
        'frequencies': frequencies,
        'spline_config': spline_config,
    }


def plot_optimization_history(history):
    """Plot optimization history.
    
    Args:
        history: List of (iteration, penalty) tuples
    """
    if not history:
        return
    
    iterations, penalties = zip(*history)
    
    plt.figure(figsize=(10, 6))
    plt.semilogy(iterations, penalties, 'b-', linewidth=2)
    plt.xlabel('Iteration')
    plt.ylabel('Penalty (log scale)')
    plt.title('Optimization History')
    plt.grid(True)
    plt.tight_layout()
    plt.show()


def plot_spline_shape(beam_config, spline_config):
    """Plot the spline shape.
    
    Args:
        beam_config: Beam configuration
        spline_config: Spline configuration
    """
    from scipy.interpolate import make_interp_spline
    
    L = beam_config.length
    x1, y1, y2 = spline_config.x1, spline_config.y1, spline_config.y2
    
    ctrl_pts = np.array([
        [0.0, 0.0],
        [x1, y1],
        [L, y2],
    ])
    
    t_knots = np.linspace(0, 1, 3)
    spl = make_interp_spline(t_knots, ctrl_pts, k=2)
    
    t = np.linspace(0, 1, 100)
    spine = spl(t)
    
    plt.figure(figsize=(10, 6))
    plt.plot(spine[:, 0], spine[:, 1], 'b-', linewidth=2, label='Spline')
    plt.plot(ctrl_pts[:, 0], ctrl_pts[:, 1], 'ro', markersize=10, label='Control points')
    plt.xlabel('x (m)')
    plt.ylabel('y (m)')
    plt.title('Spline Beam Shape')
    plt.legend()
    plt.grid(True)
    plt.axis('equal')
    plt.tight_layout()
    plt.show()
