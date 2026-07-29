"""Rayleigh-quotient eigenvalue refinement.

Both backends use shift-invert, whose back-transform from the transformed
eigenvalue theta amplifies its error by (lambda-sigma)^2.  The pencil
Rayleigh quotient of the returned eigenvector is the variationally optimal
eigenvalue for that vector (error quadratic in the eigenvector error) and
restores dense-reference accuracy.
"""

import numpy as np


def rayleigh_refine(
    A,
    B,
    eigenvalues: np.ndarray,
    vectors,
) -> np.ndarray:
    """Refine eigenvalues via Rayleigh quotient: lambda <- v^T A v / v^T B v.

    Args:
        A: Stiffness matrix (sparse or dense).
        B: Mass matrix (sparse or dense).
        eigenvalues: Raw eigenvalues from the eigensolver.
        vectors: List of full eigenvectors (one per eigenvalue).

    Returns:
        Array of refined eigenvalues.
    """
    refined = []
    for lam, vec in zip(eigenvalues, vectors):
        denom = float(vec @ (B @ vec))
        refined.append(float(vec @ (A @ vec)) / denom if denom > 0 else lam)
    return np.array(refined)
