"""FEniCSx modal analysis solver for eigenfrequency computation."""

import numpy as np
from scipy.sparse.linalg import eigsh
from mpi4py import MPI

import ufl
from dolfinx import fem, mesh, log
from dolfinx.io import XDMFFile

from config import BeamConfig, SolverConfig, OutputConfig


class ModalSolver:
    """Modal analysis solver using FEniCSx and SLEPc."""

    def __init__(
        self,
        beam_config: BeamConfig,
        solver_config: SolverConfig,
        output_config: OutputConfig,
        boundary_type: str = "cantilever",
    ):
        self.beam = beam_config
        self.solver = solver_config
        self.output = output_config
        self.boundary_type = boundary_type

    def create_mesh(self) -> mesh.Mesh:
        """Load mesh from Gmsh .msh file."""
        from dolfinx.io import gmsh

        msh_file = f"{self.output.output_dir}/beam.msh"
        mesh_data = gmsh.read_from_msh(msh_file, MPI.COMM_WORLD, rank=0, gdim=3)
        return mesh_data.mesh

    def apply_bc(self, V: fem.FunctionSpace):
        """Apply boundary conditions based on boundary_type.

        Args:
            V: Function space

        Returns:
            DirichletBC object
        """
        domain = V.mesh
        if self.boundary_type == "cantilever":
            # Fix only x=0
            facets = mesh.locate_entities_boundary(domain, 2, lambda x: np.isclose(x[0], 0.0))
        elif self.boundary_type == "clamped-clamped":
            # Fix both x=0 and x=L
            facets = mesh.locate_entities_boundary(
                domain, 2,
                lambda x: np.isclose(x[0], 0.0) | np.isclose(x[0], self.beam.length)
            )
        else:
            raise ValueError(f"Unknown boundary_type: {self.boundary_type}. Use 'cantilever' or 'clamped-clamped'.")
        dofs = fem.locate_dofs_topological(V, 2, facets)
        u_bc = fem.Function(V)
        u_bc.x.array[:] = 0.0
        return fem.dirichletbc(u_bc, dofs)

    def solve(self) -> tuple:
        """Solve the modal analysis problem.

        Returns:
            Tuple of (eigenvalues, eigenvectors)
        """
        log.set_log_level(log.LogLevel.INFO)

        domain = self.create_mesh()
        domain.topology.create_connectivity(1, 3)
        V = fem.functionspace(domain, ("Lagrange", 2, (3,)))

        u = ufl.TrialFunction(V)
        v = ufl.TestFunction(V)

        E = self.beam.youngs_modulus
        rho = self.beam.density
        # Use Poisson ratio = 0 for exact comparison with Euler-Bernoulli theory
        nu = 0.0
        mu = E / (2 * (1 + nu))
        lmbda = E * nu / ((1 + nu) * (1 - 2 * nu))

        def epsilon(u):
            return ufl.sym(ufl.grad(u))

        def sigma(u):
            return lmbda * ufl.tr(epsilon(u)) * ufl.Identity(3) + 2 * mu * epsilon(u)

        a = ufl.inner(sigma(u), epsilon(v)) * ufl.dx
        b = rho * ufl.dot(u, v) * ufl.dx

        a_form = fem.form(a)
        b_form = fem.form(b)
        bc = self.apply_bc(V)
        A_csr = fem.assemble_matrix(a_form, bcs=[bc])
        B_csr = fem.assemble_matrix(b_form)

        # Convert to scipy sparse matrices
        import scipy.sparse
        A_scipy = A_csr.to_scipy()
        B_scipy = B_csr.to_scipy()

        # Get BC DOFs to remove them from the system
        dof_indices_result = bc.dof_indices()
        if isinstance(dof_indices_result, tuple):
            bc_dofs = dof_indices_result[0]
        else:
            bc_dofs = dof_indices_result
        bc_dofs = np.array(bc_dofs)

        # Remove BC DOFs from matrices
        free_dofs = np.setdiff1d(np.arange(A_scipy.shape[0]), bc_dofs)
        
        # Convert to dense to extract submatrices (memory intensive but reliable)
        A_dense = A_scipy.toarray()
        B_dense = B_scipy.toarray()
        A_reduced = A_dense[np.ix_(free_dofs, free_dofs)]
        B_reduced = B_dense[np.ix_(free_dofs, free_dofs)]
        
        # Convert back to sparse for eigsh
        A_reduced = scipy.sparse.csr_matrix(A_reduced)
        B_reduced = scipy.sparse.csr_matrix(B_reduced)

        num_eigenvalues = min(self.solver.num_eigenvalues, A_reduced.shape[0] - 1)

        # Solve generalized eigenvalue problem using scipy
        # Use shift-invert to find smallest eigenvalues
        try:
            eigenvalues, eigenvectors = eigsh(
                A_reduced, k=num_eigenvalues, M=B_reduced,
                sigma=0.0, which='LM', tol=self.solver.tolerance
            )
        except Exception as e:
            # Fallback: try without shift-invert
            eigenvalues, eigenvectors = eigsh(
                A_reduced, k=num_eigenvalues, M=B_reduced,
                which='SM', tol=self.solver.tolerance
            )

        # Reconstruct full eigenvectors with zeros for BC DOFs
        computed_eigenvectors = []
        for i in range(len(eigenvalues)):
            full_ev = np.zeros(A_scipy.shape[0])
            full_ev[free_dofs] = eigenvectors[:, i]
            computed_eigenvectors.append(full_ev)

        return eigenvalues, computed_eigenvectors

    def compute_frequencies(self, eigenvalues: np.ndarray) -> np.ndarray:
        """Convert eigenvalues to frequencies in Hz."""
        return np.sqrt(np.real(eigenvalues)) / (2 * np.pi)

    def save_results(self, frequencies: np.ndarray, eigenvectors=None):
        """Save results to files."""
        if self.output.save_xdmf:
            pass
