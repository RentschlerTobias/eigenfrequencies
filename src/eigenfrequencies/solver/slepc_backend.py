"""SLEPc backend for the modal solver.

Free-free shift-invert with sigma=-1.0 and MUMPS direct factorization.
Falls back to CG+GAMG if the direct factorization fails (e.g. OOM).
The shifted operator is SPD, so no rigid-body nullspace is attached.
"""

import numpy as np

from eigenfrequencies.solver.exceptions import SolverConfigError


def solve_slepc(
    a_form,
    b_form,
    solver_config,
):
    """Free-free eigenproblem via SLEPc shift-invert (scales past ~1M DOFs).

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

    Returns:
        Tuple of (eigenvalues, full_vectors) where full_vectors is a list
        of full-length eigenvectors.
    """
    try:
        from petsc4py import PETSc
        from slepc4py import SLEPc
        from dolfinx.fem import petsc as fem_petsc
    except ImportError as exc:
        raise SolverConfigError(
            "SLEPc backend requested but petsc4py/slepc4py are not available."
        ) from exc

    K = fem_petsc.assemble_matrix(a_form, bcs=[])
    K.assemble()
    M = fem_petsc.assemble_matrix(b_form, bcs=[])
    M.assemble()
    n = K.getSize()[0]
    k = min(solver_config.num_eigenvalues, n - 1)
    if k <= 0:
        raise SolverConfigError(
            f"Cannot request {solver_config.num_eigenvalues} eigenvalues "
            f"with only {n} system DOFs."
        )
    print(f"[solver] system DOFs={n} (SLEPc, no DOF restriction)")

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
