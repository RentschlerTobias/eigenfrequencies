"""SciPy sparse backend for the modal solver.

Clamped path: sparse free-DOF slice, no densification.
Free-free path: shift-invert with sigma=-1.0 to handle the singular stiffness matrix.
"""

import numpy as np
from scipy.sparse.linalg import eigsh

from eigenfrequencies.solver.exceptions import SolverConfigError


def solve_scipy(
    a_form,
    b_form,
    bc,
    bc_dofs,
    solver_config,
    bc_mode: str,
):
    """Solve the generalized eigenproblem using scipy.sparse.linalg.eigsh.

    Args:
        a_form: UFL stiffness form assembled as a dolfinx fem form.
        b_form: UFL mass form assembled as a dolfinx fem form.
        bc: DirichletBC object or None.
        bc_dofs: Array of constrained DOF indices.
        solver_config: SolverConfig dataclass.
        bc_mode: BCConfig.mode string ("free", "axial_plane", "radius_band").

    Returns:
        Tuple of (eigenvalues, full_vectors) where full_vectors is a list of
        full-length eigenvectors with zeros inserted for constrained DOFs.
    """
    from dolfinx import fem

    A_scipy = fem.assemble_matrix(a_form, bcs=[bc] if bc is not None else []).to_scipy().tocsr()
    B_scipy = fem.assemble_matrix(b_form).to_scipy().tocsr()

    n = A_scipy.shape[0]
    free = np.setdiff1d(np.arange(n), bc_dofs)
    # Sparse free-DOF restriction (no densification -> scales to large meshes).
    A_red = A_scipy[free][:, free]
    B_red = B_scipy[free][:, free]
    print(f"[solver] system DOFs={n}, free DOFs={free.size}")

    k = min(solver_config.num_eigenvalues, A_red.shape[0] - 1)
    if k <= 0:
        raise SolverConfigError(
            f"Cannot request {solver_config.num_eigenvalues} eigenvalues "
            f"with only {A_red.shape[0]} free DOFs."
        )

    if bc_mode == "free":
        # Free-free K is singular (6 rigid modes at 0). A small negative
        # shift makes K - sigma*M = K + |sigma|*M positive definite, so
        # shift-invert stays well-conditioned and returns the zeros plus
        # the lowest elastic modes. sigma=0 would fail; which="SM" (the
        # clamped fallback) is prohibitively slow at this size.
        eigenvalues, eigenvectors = eigsh(
            A_red, k=k, M=B_red, sigma=-1.0, which="LM", tol=solver_config.tolerance
        )
    else:
        try:
            eigenvalues, eigenvectors = eigsh(
                A_red, k=k, M=B_red, sigma=0.0, which="LM", tol=solver_config.tolerance
            )
        except Exception:
            eigenvalues, eigenvectors = eigsh(
                A_red, k=k, M=B_red, which="SM", tol=solver_config.tolerance
            )

    order = np.argsort(eigenvalues)
    eigenvalues = eigenvalues[order]
    eigenvectors = eigenvectors[:, order]

    full_vectors = []
    for i in range(len(eigenvalues)):
        full = np.zeros(n)
        full[free] = eigenvectors[:, i]
        full_vectors.append(full)

    return eigenvalues, full_vectors
