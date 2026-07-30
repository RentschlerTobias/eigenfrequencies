"""Analytical eigenfrequencies for beam modal analysis.

Euler-Bernoulli beam theory for various boundary conditions.
Characteristic equations:
- cantilever (clamped-free): cos(alpha) * cosh(alpha) = -1
- clamped-clamped: cos(alpha) * cosh(alpha) = 1
- free-free: cos(alpha) * cosh(alpha) = 1
"""

import numpy as np


def _root(*args, **kwargs):
    """Lazy wrapper around scipy.optimize.root."""
    from scipy.optimize import root as _scipy_root
    return _scipy_root(*args, **kwargs)


def cantilever_eigenvalue_equation(alpha: float) -> float:
    """Cantilever beam eigenvalue equation: cos(alpha) * cosh(alpha) = -1."""
    return np.cos(alpha) * np.cosh(alpha) + 1


def clamped_clamped_eigenvalue_equation(alpha: float) -> float:
    """Clamped-clamped beam eigenvalue equation: cos(alpha) * cosh(alpha) = 1."""
    return np.cos(alpha) * np.cosh(alpha) - 1


def free_free_eigenvalue_equation(alpha: float) -> float:
    """Free-free beam eigenvalue equation: cos(alpha) * cosh(alpha) = 1."""
    return np.cos(alpha) * np.cosh(alpha) - 1


def compute_alpha_values(num_modes: int = 10, boundary_type: str = "cantilever") -> np.ndarray:
    """Compute the alpha values for a given boundary condition.

    Args:
        num_modes: Number of modes to compute.
        boundary_type: One of "cantilever", "clamped-clamped", "free-free".

    Returns:
        Array of alpha values.
    """
    if boundary_type == "cantilever":
        equation = cantilever_eigenvalue_equation
        x0s = [1.875, 4.694, 7.855]
        x0s += [(2 * n + 1) * np.pi / 2 for n in range(3, num_modes)]
    elif boundary_type == "clamped-clamped":
        equation = clamped_clamped_eigenvalue_equation
        x0s = [(2 * n + 1) * np.pi / 2 for n in range(num_modes)]
    elif boundary_type == "free-free":
        equation = free_free_eigenvalue_equation
        x0s = [(2 * n + 1) * np.pi / 2 for n in range(num_modes)]
    else:
        raise ValueError(f"Unknown boundary_type: {boundary_type}")

    alphas = []
    for x0 in x0s[:num_modes]:
        sol = _root(equation, x0)
        alphas.append(sol.x[0] if sol.success else x0)
    return np.array(alphas)


def analytical_frequencies_cantilever(beam, num_modes: int = 10, axis: str = "y") -> np.ndarray:
    """Compute analytical eigenfrequencies for a cantilever beam.

    Uses Euler-Bernoulli beam theory.

    Args:
        beam: Beam configuration (must have youngs_modulus, density, length,
            cross_section_area, moment_of_inertia_y, moment_of_inertia_z).
        num_modes: Number of modes to compute.
        axis: Bending axis ("y" or "z").

    Returns:
        Array of frequencies in Hz.
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

    alphas = compute_alpha_values(num_modes, boundary_type="cantilever")
    frequencies = []
    for alpha in alphas:
        omega = alpha**2 * np.sqrt(E * I / (rho * S * L**4))
        frequencies.append(omega / (2 * np.pi))
    return np.array(frequencies)


def classify_mode(eigenvector, mesh_coords):
    """Classify vibration mode based on displacement pattern.

    Args:
        eigenvector: Eigenvector array (num_dofs).
        mesh_coords: Node coordinates (num_nodes, 3).

    Returns:
        dict with mode classification.
    """
    num_nodes = len(mesh_coords)

    if len(eigenvector) >= num_nodes * 3:
        u = eigenvector[:num_nodes * 3].reshape((num_nodes, 3))
    else:
        u = eigenvector.reshape((-1, 3))

    ux = u[:, 0]
    uy = u[:, 1]
    uz = u[:, 2]

    max_ux = np.max(np.abs(ux))
    max_uy = np.max(np.abs(uy))
    max_uz = np.max(np.abs(uz))

    displacements = {"x": max_ux, "y": max_uy, "z": max_uz}
    dominant = max(displacements, key=displacements.get)

    y_coords = mesh_coords[:, 1]
    z_coords = mesh_coords[:, 2]

    top_mask = z_coords > 0
    bottom_mask = z_coords < 0

    if np.any(top_mask) and np.any(bottom_mask):
        uz_top = uz[top_mask]
        uz_bottom = uz[bottom_mask]
        torsion_indicator = np.abs(np.mean(uz_top) - np.mean(uz_bottom))
    else:
        torsion_indicator = 0

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


def analytical_frequencies(
    beam, num_modes: int = 10, clamped_left: bool = True, clamped_right: bool = True
) -> list:
    """Compute analytical eigenfrequencies for beam boundary conditions.

    Args:
        beam: Beam configuration.
        num_modes: Number of modes to compute.
        clamped_left: True if clamped at x=0.
        clamped_right: True if clamped at x=L.

    Returns:
        List of frequencies in Hz.
    """
    E = beam.youngs_modulus
    rho = beam.density
    L = beam.length
    I = beam.moment_of_inertia_y
    S = beam.cross_section_area

    if clamped_left and clamped_right:
        boundary_type = "clamped-clamped"
    elif clamped_left and not clamped_right:
        boundary_type = "cantilever"
    elif not clamped_left and clamped_right:
        boundary_type = "cantilever"  # same as clamped-free
    else:
        boundary_type = "free-free"

    alphas = compute_alpha_values(num_modes, boundary_type=boundary_type)
    frequencies = []
    for alpha in alphas:
        omega = alpha**2 * np.sqrt(E * I / (rho * S * L**4))
        frequencies.append(omega / (2 * np.pi))
    return frequencies
