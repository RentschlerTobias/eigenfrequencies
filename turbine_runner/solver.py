"""STAGE 2b: structural modal solver for the turbine runner.

Self-contained adaptation of ``demo/beam/solver.py``. The weak form, P2 vector
space and Hz conversion are reused verbatim, but two things differ:

1. Boundary conditions come from a config-driven coordinate predicate at the hub
   (the beam hardcodes x=0).
2. The BC-DOF removal stays fully sparse. The beam densifies both matrices
   (``A_scipy.toarray()`` at solver.py:117), which OOMs at runner scale
   (~10^5-10^6 P2 DOFs). Here the free-DOF restriction slices CSR matrices.
"""

import numpy as np
import scipy.sparse
from scipy.sparse.linalg import eigsh

import ufl
from dolfinx import fem, mesh as dmesh

from config import MaterialConfig, BCConfig, SolverConfig


_AXIS_INDEX = {"x": 0, "y": 1, "z": 2}


class RunnerModalSolver:
    """Modal analysis of a runner volume mesh with a hub clamp."""

    def __init__(
        self,
        domain,
        material: MaterialConfig,
        bc_config: BCConfig,
        solver_config: SolverConfig,
    ):
        self.domain = domain
        self.material = material
        self.bc = bc_config
        self.solver = solver_config
        self.V = None

    def _bc_predicate(self):
        """Build the hub-clamp coordinate predicate from BCConfig."""
        cfg = self.bc
        if cfg.mode == "free":
            return None
        if cfg.axis not in _AXIS_INDEX:
            raise ValueError(f"BCConfig.axis must be x/y/z, got {cfg.axis!r}")
        ai = _AXIS_INDEX[cfg.axis]
        p, q = [i for i in range(3) if i != ai]
        c1, c2 = cfg.hub_center

        if cfg.mode == "axial_plane":
            def predicate(x):
                return np.isclose(x[ai], cfg.plane_value, atol=cfg.plane_tol)
            return predicate

        if cfg.mode == "radius_band":
            def predicate(x):
                radius = np.sqrt((x[p] - c1) ** 2 + (x[q] - c2) ** 2)
                sel = radius <= cfg.hub_radius
                if cfg.axial_min is not None:
                    sel = sel & (x[ai] >= cfg.axial_min)
                if cfg.axial_max is not None:
                    sel = sel & (x[ai] <= cfg.axial_max)
                return sel
            return predicate

        raise ValueError(f"BCConfig.mode must be 'radius_band' or 'axial_plane', got {cfg.mode!r}")

    def apply_bc(self, V):
        """Clamp the hub region; verify a non-empty, plausible clamp.

        mode="free" (experimental validation, free-free suspension): no clamp at
        all; returns (None, empty) so solve() skips the DOF restriction.
        """
        if self.bc.mode == "free":
            print("[solver] free-free BC: no DOFs clamped (rigid modes expected)")
            return None, np.array([], dtype=np.int32)
        tdim = self.domain.topology.dim
        facets = dmesh.locate_entities_boundary(self.domain, tdim - 1, self._bc_predicate())
        dofs = fem.locate_dofs_topological(V, tdim - 1, facets)

        u_bc = fem.Function(V)
        u_bc.x.array[:] = 0.0
        bc = fem.dirichletbc(u_bc, dofs)

        dof_indices = bc.dof_indices()
        bc_dofs = np.array(dof_indices[0] if isinstance(dof_indices, tuple) else dof_indices)
        n_fixed = bc_dofs.size
        print(f"[solver] clamped facets={facets.size}, fixed DOFs={n_fixed}")
        if n_fixed == 0:
            raise RuntimeError(
                "No DOFs were clamped. The hub BC region missed the mesh; re-run the "
                "axis-discovery diagnostic and fix BCConfig (axis / hub_radius / axial band)."
            )
        # Report the clamped-node bounding box so the user can confirm it is the hub.
        coords = V.tabulate_dof_coordinates()
        clamped_nodes = np.unique(bc_dofs // V.dofmap.index_map_bs)
        clamped_xyz = coords[clamped_nodes]
        bbox_lo = clamped_xyz.min(axis=0)
        bbox_hi = clamped_xyz.max(axis=0)
        print(f"[solver] clamped-node bbox: min={bbox_lo}, max={bbox_hi}")
        return bc, bc_dofs

    def solve(self) -> tuple:
        """Assemble and solve the generalized eigenproblem (sparse throughout)."""
        domain = self.domain
        domain.topology.create_connectivity(domain.topology.dim - 1, domain.topology.dim)
        V = fem.functionspace(domain, ("Lagrange", self.solver.element_degree, (3,)))
        self.V = V

        u = ufl.TrialFunction(V)
        v = ufl.TestFunction(V)

        E = self.material.youngs_modulus
        rho = self.material.density
        nu = self.material.poisson_ratio
        mu = E / (2 * (1 + nu))
        lmbda = E * nu / ((1 + nu) * (1 - 2 * nu))

        def epsilon(w):
            return ufl.sym(ufl.grad(w))

        def sigma(w):
            return lmbda * ufl.tr(epsilon(w)) * ufl.Identity(3) + 2 * mu * epsilon(w)

        a_form = fem.form(ufl.inner(sigma(u), epsilon(v)) * ufl.dx)
        b_form = fem.form(rho * ufl.dot(u, v) * ufl.dx)

        bc, bc_dofs = self.apply_bc(V)

        if self.solver.solver_backend == "slepc":
            if self.bc.mode != "free":
                raise ValueError(
                    "solver_backend='slepc' supports mode='free' only; "
                    "use 'scipy' for clamped BCs"
                )
            self.backend_used = "slepc"
            eigenvalues, full_vectors = self._solve_slepc(a_form, b_form)
            self._rigid_body_check(eigenvalues)
            return eigenvalues, full_vectors
        if self.solver.solver_backend != "scipy":
            raise ValueError(
                "SolverConfig.solver_backend must be 'scipy' or 'slepc', "
                f"got {self.solver.solver_backend!r}"
            )
        self.backend_used = "scipy"

        A_scipy = fem.assemble_matrix(a_form, bcs=[bc] if bc is not None else []).to_scipy().tocsr()
        B_scipy = fem.assemble_matrix(b_form).to_scipy().tocsr()

        n = A_scipy.shape[0]
        free = np.setdiff1d(np.arange(n), bc_dofs)
        # Sparse free-DOF restriction (no densification -> scales to large meshes).
        A_red = A_scipy[free][:, free]
        B_red = B_scipy[free][:, free]
        print(f"[solver] system DOFs={n}, free DOFs={free.size}")

        k = min(self.solver.num_eigenvalues, A_red.shape[0] - 1)
        if self.bc.mode == "free":
            # Free-free K is singular (6 rigid modes at 0). A small negative
            # shift makes K - sigma*M = K + |sigma|*M positive definite, so
            # shift-invert stays well-conditioned and returns the zeros plus
            # the lowest elastic modes. sigma=0 would fail; which="SM" (the
            # clamped fallback) is prohibitively slow at this size.
            eigenvalues, eigenvectors = eigsh(
                A_red, k=k, M=B_red, sigma=-1.0, which="LM", tol=self.solver.tolerance
            )
        else:
            try:
                eigenvalues, eigenvectors = eigsh(
                    A_red, k=k, M=B_red, sigma=0.0, which="LM", tol=self.solver.tolerance
                )
            except Exception:
                eigenvalues, eigenvectors = eigsh(
                    A_red, k=k, M=B_red, which="SM", tol=self.solver.tolerance
                )

        order = np.argsort(eigenvalues)
        eigenvalues = eigenvalues[order]
        eigenvectors = eigenvectors[:, order]

        full_vectors = []
        for i in range(len(eigenvalues)):
            full = np.zeros(n)
            full[free] = eigenvectors[:, i]
            full_vectors.append(full)

        eigenvalues = self._rayleigh_refine(A_scipy, B_scipy, eigenvalues, full_vectors)

        self._rigid_body_check(eigenvalues)
        return eigenvalues, full_vectors

    def _solve_slepc(self, a_form, b_form) -> tuple:
        """Free-free eigenproblem via SLEPc shift-invert (scales past ~1M DOFs).

        Same shifted operator as the scipy branch: with sigma=-1 the matrix
        K - sigma*M = K + M is SPD (K PSD, M SPD), so a direct MUMPS
        factorization is well-posed and the lowest eigenvalues (rigid modes
        first, then elastic) map to the largest transformed ones. Falls back
        to CG+GAMG if the direct factorization fails (e.g. OOM); the shifted
        operator is SPD, so no rigid-body nullspace is attached.
        """
        from petsc4py import PETSc
        from slepc4py import SLEPc
        from dolfinx.fem import petsc as fem_petsc

        K = fem_petsc.assemble_matrix(a_form, bcs=[])
        K.assemble()
        M = fem_petsc.assemble_matrix(b_form, bcs=[])
        M.assemble()
        n = K.getSize()[0]
        k = min(self.solver.num_eigenvalues, n - 1)
        print(f"[solver] system DOFs={n} (SLEPc, no DOF restriction)")

        eps = SLEPc.EPS().create()
        eps.setOperators(K, M)
        eps.setProblemType(SLEPc.EPS.ProblemType.GHEP)
        eps.setWhichEigenpairs(SLEPc.EPS.Which.TARGET_MAGNITUDE)
        eps.setDimensions(nev=k, ncv=max(2 * k + 1, k + 16))
        eps.setTolerances(tol=self.solver.tolerance, max_it=200)
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
            print(f"[solver] direct factorization failed ({err}); "
                  "retrying with CG+GAMG")
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

    @staticmethod
    def _rayleigh_refine(A, B, eigenvalues, vectors) -> np.ndarray:
        """Rayleigh-quotient refinement: lambda <- v^T A v / v^T B v.

        Both backends use shift-invert, whose back-transform from the
        transformed eigenvalue theta amplifies its error by (lambda-sigma)^2;
        the pencil Rayleigh quotient of the returned eigenvector is the
        variationally optimal eigenvalue for that vector (error quadratic in
        the eigenvector error) and restores dense-reference accuracy.
        """
        refined = []
        for lam, vec in zip(eigenvalues, vectors):
            denom = float(vec @ (B @ vec))
            refined.append(float(vec @ (A @ vec)) / denom if denom > 0 else lam)
        return np.array(refined)

    def _rigid_body_check(self, eigenvalues: np.ndarray) -> None:
        """Check rigid-body modes: expected (6) in free mode, failure when clamped."""
        freqs = self.compute_frequencies(eigenvalues)
        near_zero = int(np.sum(freqs < 1e-3))
        if self.bc.mode == "free":
            print(f"[solver] {near_zero} rigid-body modes (6 expected for one "
                  "connected body; more suggests disconnected parts in the mesh)")
            return
        if near_zero > 0:
            print(f"[solver] WARNING: {near_zero} near-zero frequencies detected. "
                  "A properly clamped runner has none; the hub clamp may be ineffective.")

    @staticmethod
    def compute_frequencies(eigenvalues: np.ndarray) -> np.ndarray:
        """Convert eigenvalues to frequencies in Hz."""
        return np.sqrt(np.abs(np.real(eigenvalues))) / (2 * np.pi)

    def wet_compare(self, eigenvalues, eigenvectors, wet_cfg) -> dict:
        """Dry-vs-wet (added-mass) frequency comparison (decision (b), DEFERRED).

        Returns dry + wet frequencies side by side. Uses added_mass.compare, which
        falls back to a placeholder added-mass ratio until the fluid Laplace solve
        is implemented (see added_mass.rayleigh_ratios / HANDOFF.md). A static fluid
        only adds mass; wet frequencies are therefore always <= dry.
        """
        from added_mass import compare
        dry = self.compute_frequencies(eigenvalues)
        return compare(dry, wet_cfg, mode_shapes=eigenvectors, domain=self.domain)
