# Showcase how to use eigenfrequencies
# Import docker (dolfinx) into iron repl :lua vim.g.iron_python_repl = "docker"
#

# =====  Mesh laden =================================================
from eigenfrequencies.config import MeshConfig
from eigenfrequencies.io import load_and_prepare_mesh

cfg = MeshConfig(msh_path="turbine_runner/assets/runner_best.msh", gdim=3)
domain = load_and_prepare_mesh(cfg)

# %%
tdim = domain.topology.dim
print("tdim  :", tdim)
print("Zellen:", domain.topology.index_map(tdim).size_local)
print("Knoten:", domain.geometry.x.shape[0])

from eigenfrequencies.io import inspect_mesh

diag = inspect_mesh(cfg, verbose=True)


# =====  Modalanalyse ===============================================
from eigenfrequencies.config import BCConfig

bc = BCConfig(mode="axial_plane", axis="z", plane_value=0.0, plane_tol=1e-6)

from eigenfrequencies.config import MaterialConfig

mat = MaterialConfig()  # Stahl: E=210 GPa, rho=7850, nu=0.30

from eigenfrequencies.config import SolverConfig

solver_cfg = SolverConfig(
    num_eigenvalues=10,  # fuer Live-Demo ggf. 4
    element_degree=2,
    solver_backend="scipy",
    tolerance=1e-6,
)

from eigenfrequencies.solver import ModalSolver


solver = ModalSolver(domain, mat, bc, solver_cfg)

eigenvalues, eigenvectors = solver.solve()

freqs = ModalSolver.compute_frequencies(eigenvalues)
for i, f in enumerate(freqs):
    print(f"Mode {i + 1:>2}: {f:7.2f} Hz")


# ===== Resonanz-Check =============================================
from eigenfrequencies.config import OptimizationConfig

opt = OptimizationConfig(
    n_rpm=72.0,  # Drehzahl
    Z_guidevanes=18,  # Leitschaufeln
    max_harmonic=6,
    margin_hz=5.0,  # +-5 Hz Mindestabstand
    margin_fraction=0.05,  # oder 5% der Mittenfrequenz
    penalty_k=1.0,
)

# %%
from eigenfrequencies.penalty import band_report, compute_penalty

penalty = compute_penalty(freqs, opt)
print(f"Penalty: {penalty:.4f}")
print(band_report(freqs, opt))
