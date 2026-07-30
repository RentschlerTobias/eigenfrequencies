"""Generic modal solver for structural eigenfrequency analysis.

The weak form, P2 vector space and Hz conversion are reused from the
original reference solver, but two things differ:

1. Boundary conditions come from a config-driven coordinate predicate; the
   caller injects BCConfig rather than hard-coding geometry.
2. The BC-DOF removal stays fully sparse. The beam demo densifies both
   matrices (``A_scipy.toarray()``), which OOMs at large scale
   (~10^5-10^6 P2 DOFs). Here the free-DOF restriction slices CSR matrices.
"""

import numpy as np

import ufl
from dolfinx import fem, mesh as dmesh

from eigenfrequencies.config import MaterialConfig, BCConfig, SolverConfig
from eigenfrequencies.solver.exceptions import SolverConfigError
from eigenfrequencies.solver.rayleigh import rayleigh_refine
from eigenfrequencies.solver.scipy_backend import solve_scipy
from eigenfrequencies.solver.slepc_backend import solve_slepc


_AXIS_INDEX = {"x": 0, "y": 1, "z": 2}


class ModalSolver:
    """Modal analysis of a 3-D volume mesh with injected boundary conditions."""

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
        self.backend_used = None

    def _bc_predicate(self):
        """Build the coordinate predicate from BCConfig."""
        cfg = self.bc
        if cfg.mode == "free":
            return None
        if cfg.axis not in _AXIS_INDEX:
            raise SolverConfigError(
                f"BCConfig.axis must be x/y/z, got {cfg.axis!r}"
            )
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

        raise SolverConfigError(
            f"BCConfig.mode must be 'radius_band', 'axial_plane', or 'free', "
            f"got {cfg.mode!r}"
        )

    def apply_bc(self, V):
        """Clamp the specified region; verify a non-empty, plausible clamp.

        mode="free" (experimental validation, free-free suspension): no clamp
        at all; returns (None, empty) so solve() skips the DOF restriction.
        """
        if self.bc.mode == "free":
            print("[solver] free-free BC: no DOFs clamped (rigid modes expected)")
            return None, np.array([], dtype=np.int32)
        tdim = self.domain.topology.dim
        facets = dmesh.locate_entities_boundary(
            self.domain, tdim - 1, self._bc_predicate()
        )
        dofs = fem.locate_dofs_topological(V, tdim - 1, facets)

        u_bc = fem.Function(V)
        u_bc.x.array[:] = 0.0
        bc = fem.dirichletbc(u_bc, dofs)

        dof_indices = bc.dof_indices()
        bc_dofs = np.array(
            dof_indices[0] if isinstance(dof_indices, tuple) else dof_indices
        )
        n_fixed = bc_dofs.size
        print(f"[solver] clamped facets={facets.size}, fixed DOFs={n_fixed}")
        if n_fixed == 0:
            raise RuntimeError(
                "No DOFs were clamped. The BC region missed the mesh; re-run the "
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
        V = fem.functionspace(
            domain, ("Lagrange", self.solver.element_degree, (3,))
        )
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
                raise SolverConfigError(
                    "solver_backend='slepc' supports mode='free' only; "
                    "use 'scipy' for clamped BCs"
                )
            self.backend_used = "slepc"
            eigenvalues, full_vectors = solve_slepc(a_form, b_form, self.solver)
            self._rigid_body_check(eigenvalues)
            return eigenvalues, full_vectors

        if self.solver.solver_backend == "scipy":
            self.backend_used = "scipy"
            eigenvalues, full_vectors = solve_scipy(
                a_form, b_form, bc, bc_dofs, self.solver, self.bc.mode
            )
            # SciPy backend returns raw eigenvalues; apply Rayleigh refinement.
            A_scipy = fem.assemble_matrix(
                a_form, bcs=[bc] if bc is not None else []
            ).to_scipy().tocsr()
            B_scipy = fem.assemble_matrix(b_form).to_scipy().tocsr()
            eigenvalues = rayleigh_refine(A_scipy, B_scipy, eigenvalues, full_vectors)
            self._rigid_body_check(eigenvalues)
            return eigenvalues, full_vectors

        raise SolverConfigError(
            "SolverConfig.solver_backend must be 'scipy' or 'slepc', "
            f"got {self.solver.solver_backend!r}"
        )

    def _rigid_body_check(self, eigenvalues: np.ndarray) -> None:
        """Check rigid-body modes: expected (6) in free mode, failure when clamped."""
        freqs = self.compute_frequencies(eigenvalues)
        near_zero = int(np.sum(freqs < 1e-3))
        if self.bc.mode == "free":
            print(
                f"[solver] {near_zero} rigid-body modes (6 expected for one "
                "connected body; more suggests disconnected parts in the mesh)"
            )
            return
        if near_zero > 0:
            print(
                f"[solver] WARNING: {near_zero} near-zero frequencies detected. "
                "A properly clamped body has none; the clamp may be ineffective."
            )

    @staticmethod
    def compute_frequencies(eigenvalues: np.ndarray) -> np.ndarray:
        """Convert eigenvalues to frequencies in Hz."""
        return np.sqrt(np.abs(np.real(eigenvalues))) / (2 * np.pi)
