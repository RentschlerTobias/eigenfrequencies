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
        """Load mesh from Gmsh .msh file."""
        from dolfinx.io import gmsh

        msh_file = f"{self.output.output_dir}/beam.msh"
        mesh_data = gmsh.read_from_msh(msh_file, MPI.COMM_WORLD, rank=0, gdim=3)
        return mesh_data.mesh

    def apply_clamped_bc(self, V: fem.FunctionSpace):
        """Apply clamped boundary condition at x=0."""
        domain = V.mesh
        facets = mesh.locate_entities_boundary(domain, 1, lambda x: np.isclose(x[0], 0.0))
        dofs = fem.locate_dofs_topological(V, 1, facets)
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
        mu = E / (2 * (1 + 0.3))
        lmbda = E * 0.3 / ((1 + 0.3) * (1 - 2 * 0.3))

        def epsilon(u):
            return ufl.sym(ufl.grad(u))

        def sigma(u):
            return lmbda * ufl.tr(epsilon(u)) * ufl.Identity(3) + 2 * mu * epsilon(u)

        a = ufl.inner(sigma(u), epsilon(v)) * ufl.dx
        b = rho * ufl.dot(u, v) * ufl.dx

        a_form = fem.form(a)
        b_form = fem.form(b)
        bc = self.apply_clamped_bc(V)
        A_csr = fem.assemble_matrix(a_form, bcs=[bc])
        B_csr = fem.assemble_matrix(b_form)

        A_dense = A_csr.to_dense()
        B_dense = B_csr.to_dense()
        m, n = A_dense.shape
        nnz = np.count_nonzero(A_dense)

        A = PETSc.Mat().createAIJ(size=(m, n), comm=MPI.COMM_WORLD)
        A.setPreallocationNNZ(nnz)
        A.setUp()
        rows, cols = np.where(A_dense != 0)
        for idx in range(len(rows)):
            A.setValue(rows[idx], cols[idx], A_dense[rows[idx], cols[idx]])
        A.assemble()

        m, n = B_dense.shape
        nnz = np.count_nonzero(B_dense)
        B = PETSc.Mat().createAIJ(size=(m, n), comm=MPI.COMM_WORLD)
        B.setPreallocationNNZ(nnz)
        B.setUp()
        rows, cols = np.where(B_dense != 0)
        for idx in range(len(rows)):
            B.setValue(rows[idx], cols[idx], B_dense[rows[idx], cols[idx]])
        B.assemble()

        num_eigenvalues = min(self.solver.num_eigenvalues, V.dofmap.index_map.size_local)

        eigensolver = SLEPc.EPS().create()
        eigensolver.setDimensions(num_eigenvalues)
        eigensolver.setOperators(A, B)
        eigensolver.setProblemType(SLEPc.EPS.ProblemType.GHEP)
        eigensolver.setTolerances(self.solver.tolerance,max_it=10000)
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
