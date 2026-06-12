"""Analytical eigenfrequencies for a cantilever beam using Euler-Bernoulli theory.

For a cantilever beam (one end clamped, one end free), the eigenvalue equation is:
    cos(alpha) * cosh(alpha) = -1

The eigenfrequencies are given by:
    f_n = alpha_n^2 / (2*pi) * sqrt(E*I / (rho * S * L^4))

where alpha_n are the solutions of the eigenvalue equation.
"""

import numpy as np
from scipy.optimize import root

from config import BeamConfig


def cantilever_eigenvalue_equation(alpha: float) -> float:
    """Cantilever beam eigenvalue equation: cos(alpha) * cosh(alpha) = -1."""
    return np.cos(alpha) * np.cosh(alpha) + 1


def compute_alpha_values(num_modes: int = 10) -> np.ndarray:
    """Compute the alpha values for a cantilever beam.
    
    Args:
        num_modes: Number of modes to compute
        
    Returns:
        Array of alpha values
    """
    alphas = []
    
    # Initial guesses for the first few modes
    # For cantilever: alpha_1 ≈ 1.875, alpha_2 ≈ 4.694, alpha_3 ≈ 7.855
    # For higher modes: alpha_n ≈ (2n - 1) * pi / 2
    
    for n in range(1, num_modes + 1):
        if n == 1:
            x0 = 1.875
        elif n == 2:
            x0 = 4.694
        elif n == 3:
            x0 = 7.855
        else:
            x0 = (2 * n - 1) * np.pi / 2
            
        sol = root(cantilever_eigenvalue_equation, x0)
        if sol.success:
            alphas.append(sol.x[0])
        else:
            alphas.append(x0)
    
    return np.array(alphas)


def analytical_frequencies_cantilever(beam: BeamConfig, num_modes: int = 10, axis: str = "y") -> np.ndarray:
    """Compute analytical eigenfrequencies for a cantilever beam.
    
    Uses Euler-Bernoulli beam theory.
    
    Args:
        beam: Beam configuration
        num_modes: Number of modes to compute
        axis: Bending axis ("y" or "z")
        
    Returns:
        Array of frequencies in Hz
    """
    E = beam.youngs_modulus
    rho = beam.density
    L = beam.length
    S = beam.cross_section_area
    
    if axis == "y":
        I = beam.moment_of_inertia_y
    elif axis == "z":
        I = beam.moment_of_inertia_z
    else:
        raise ValueError(f"Unknown axis: {axis}. Use 'y' or 'z'.")
    
    alphas = compute_alpha_values(num_modes)
    
    frequencies = []
    for alpha in alphas:
        omega = alpha**2 * np.sqrt(E * I / (rho * S * L**4))
        frequencies.append(omega / (2 * np.pi))
    
    return np.array(frequencies)
