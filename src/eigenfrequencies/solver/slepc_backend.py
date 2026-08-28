"""SLEPc backend for the modal solver.

Shift-invert with sigma=-1.0 and MUMPS direct factorization, for the free-free
and the clamped case alike. Falls back to CG+GAMG if the direct factorization
fails (e.g. OOM). The shifted operator is SPD, so no rigid-body nullspace is
attached.

Clamped boundary conditions are handled by assembly rather than by removing
DOFs: the constrained rows get a unit diagonal in K and a **zero** diagonal in
M, so their eigenvalue is 1/0 — infinite. Under shift-invert an infinite
eigenvalue maps to theta = 0, the smallest transformed magnitude, so the
spurious modes end up at the far end of the spectrum the solver is searching
and never compete with the physical ones. This keeps the sparse structure
intact, which is the whole reason for using SLEPc instead of slicing the
matrices as the scipy backend does.
"""

import numpy as np

from eigenfrequencies.solver.exceptions import SolverConfigError

#: Diagonal entries written into the constrained rows. K gets 1, M gets 0 —
#: see the module docstring for why that banishes the spurious modes.
_BC_DIAG_K = 1.0
_BC_DIAG_M = 0.0

#: Eigenvalues above this are the constrained rows showing up as a finite but
#: enormous number instead of an exact infinity. They are not modes.
_SPURIOUS_ABOVE = 1e30


def solve_slepc(
    a_form,
    b_form,
    solver_config,
    bc=None,
):
    """Eigenproblem via SLEPc shift-invert (scales past ~1M DOFs).

    Same shifted operator as the scipy branch: with sigma=-1 the matrix
    K - sigma*M = K + M is SPD (K PSD, M SPD), so a direct MUMPS
    factorization is well-posed and the lowest eigenvalues (rigid modes
    first, then elastic) map to the largest transformed ones. Falls back
    to CG+GAMG if the direct factorization fails (e.g. OOM); the shifted
    operator is SPD, so no rigid-body nullspace is attached.

    Args:
        a_form: UFL stiffness form assembled as a dolfinx fem form.
        b_form: UFL mass form assembled as a dolfinx fem form.
        solver_config: SolverConfig dataclass.
        bc: Optional dolfinx DirichletBC. ``None`` is the free-free case.

    Returns:
        Tuple of (eigenvalues, full_vectors) where full_vectors is a list
        of full-length eigenvectors.
    """
    try:
        from dolfinx.fem import petsc as fem_petsc
        from petsc4py import PETSc
        from slepc4py import SLEPc
    except ImportError as exc:
        raise SolverConfigError(
            "SLEPc backend requested but petsc4py/slepc4py are not available."
        ) from exc

    bcs = [bc] if bc is not None else []
    K = fem_petsc.assemble_matrix(a_form, bcs=bcs, diag=_BC_DIAG_K)
    K.assemble()
    M = fem_petsc.assemble_matrix(b_form, bcs=bcs, diag=_BC_DIAG_M)
    M.assemble()
    n = K.getSize()[0]
    k = min(solver_config.num_eigenvalues, n - 1)
    if k <= 0:
        raise SolverConfigError(
            f"Cannot request {solver_config.num_eigenvalues} eigenvalues "
            f"with only {n} system DOFs."
        )
    clamp = "clamped" if bcs else "free-free"
    print(f"[solver] system DOFs={n} (SLEPc, {clamp}, no DOF restriction)")

    eps = SLEPc.EPS().create()
    eps.setOperators(K, M)
    eps.setProblemType(SLEPc.EPS.ProblemType.GHEP)
    eps.setWhichEigenpairs(SLEPc.EPS.Which.TARGET_MAGNITUDE)
    eps.setDimensions(nev=k, ncv=max(2 * k + 1, k + 16))
    eps.setTolerances(tol=solver_config.tolerance, max_it=200)
    st = eps.getST()
    st.setType(SLEPc.ST.Type.SINVERT)
    eps.setTarget(-1.0)
    st.setShift(-1.0)

    ksp = st.getKSP()
    ksp.setType(PETSc.KSP.Type.PREONLY)
    pc = ksp.getPC()
    pc.setType(PETSc.PC.Type.LU)
    pc.setFactorSolverType("mumps")

    try:
        eps.solve()
    except PETSc.Error as err:
        print(f"[solver] direct factorization failed ({err}); retrying with CG+GAMG")
        ksp.setType(PETSc.KSP.Type.CG)
        pc.setType(PETSc.PC.Type.GAMG)
        eps.solve()

    nconv = eps.getConverged()
    print(f"[solver] SLEPc converged eigenpairs: {nconv}/{k}")
    if nconv == 0:
        raise RuntimeError("SLEPc found no converged eigenpairs")

    xr, xi = K.createVecs()
    kv, mv = K.createVecs()
    pairs = []
    for i in range(min(k, nconv)):
        lam = float(np.real(eps.getEigenpair(i, xr, xi)))
        K.mult(xr, kv)
        M.mult(xr, mv)
        denom = float(np.real(xr.dot(mv)))
        rq = float(np.real(xr.dot(kv))) / denom if denom > 0 else lam
        # A clamped DOF carries no mass, so its Rayleigh quotient is a division
        # by (almost) zero. Those are the constrained rows, not modes.
        if not np.isfinite(rq) or abs(rq) > _SPURIOUS_ABOVE:
            continue
        pairs.append((rq, xr.getArray().copy()))
    kv.destroy()
    mv.destroy()
    xr.destroy()
    xi.destroy()
    eps.destroy()
    K.destroy()
    M.destroy()

    pairs.sort(key=lambda p: p[0])
    eigenvalues = np.array([p[0] for p in pairs])
    full_vectors = [p[1] for p in pairs]
    return eigenvalues, full_vectors
