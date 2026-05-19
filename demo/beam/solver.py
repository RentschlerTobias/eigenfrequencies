"""FEniCSx modal analysis solver for eigenfrequency computation."""

import numpy as np
from mpi4py import MPI
from petsc4py import PETSc
from slepc4py import SLEPc

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
    ):
        self.beam = beam_config
        self.solver = solver_config
        self.output = output_config

    def create_mesh(self) -> mesh.Mesh:
        """Load mesh from XDMF file."""
        from dolfinx.io import gmshio

        msh_file = f"{self.output.output_dir}/beam.msh"
        mesh, _, _ = gmshio.read_msh(msh_file, rank=0)
        return mesh

    def apply_clamped_bc(self, V: fem.FunctionSpace):
        """Apply clamped boundary condition at x=0."""
        dofs = fem.locate_dofs_geometrical(V, lambda x: np.isclose(x[0], 0.0))
        u_bc = fem.Function(V)
        with u_bc.vector.localForm() as u_local:
            u_local.set(0.0)
        return fem.bc.DirichletBC(u_bc, dofs)

    def solve(self) -> tuple:
        """Solve the modal analysis problem.

        Returns:
            Tuple of (eigenvalues, eigenvectors)
        """
        log.set_log_level(log.LogLevel.INFO)

        domain = self.create_mesh()
        V = fem.functionspace(domain, ("Lagrange", 2))

        u = ufl.TrialFunction(V)
        v = ufl.TestFunction(V)

        E = self.beam.youngs_modulus
        rho = self.beam.density
        mu = E / (2 * (1 + 0.3))
        lmbda = E * 0.3 / ((1 + 0.3) * (1 - 2 * 0.3))

        def epsilon(u):
            return ufl.sym(ufl.grad(u))

        def sigma(u):
            return lmbda * ufl.tr(epsilon(u)) * ufl.Identity(3) + 2 * mu * epsilon(u)

        a = ufl.inner(sigma(u), epsilon(v)) * ufl.dx
        b = rho * ufl.dot(u, v) * ufl.dx

        A = fem.assemble_matrix(a)
        B = fem.assemble_matrix(b)
        A.assemble()
        B.assemble()

        bc = self.apply_clamped_bc(V)
        bc.apply(A)

        num_eigenvalues = min(self.solver.num_eigenvalues, V.dofmap.index_map.size)

        eigensolver = SLEPc.EPS().create()
        eigensolver.setDimensions(num_eigenvalues)
        eigensolver.setOperators(A, B)
        eigensolver.setProblemType(SLEPc.EPS.ProblemType.GENERALIZED_HERMITIAN)
        eigensolver.setTolerances(self.solver.tolerance)
        eigensolver.setWhichEigenpairs(SLEPc.EPS.Which.TARGET_MAGNITUDE)

        target_freq = (self.solver.freq_min + self.solver.freq_max) / 2
        eigensolver.setTarget(target_freq**2)
        eigensolver.solve()

        computed_eigenvalues = []
        computed_eigenvectors = []

        nconv = eigensolver.getConverged()
        for i in range(min(nconv, num_eigenvalues)):
            eigenvalue = eigensolver.getEigenvalue(i)
            computed_eigenvalues.append(eigenvalue)

        return computed_eigenvalues, None

    def compute_frequencies(self, eigenvalues: np.ndarray) -> np.ndarray:
        """Convert eigenvalues to frequencies in Hz."""
        return np.sqrt(np.real(eigenvalues)) / (2 * np.pi)

    def save_results(self, frequencies: np.ndarray, eigenvectors=None):
        """Save results to files."""
        if self.output.save_xdmf:
            pass