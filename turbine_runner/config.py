"""Configuration for hydraulic turbine runner modal analysis.

Mirrors the dataclass style of ``demo/beam/config.py`` but targets an externally
generated runner mesh (from dtOO) instead of a parametric beam.
"""

import os
from dataclasses import dataclass
from typing import Optional, Tuple


_HERE = os.path.dirname(os.path.abspath(__file__))


@dataclass
class MaterialConfig:
    """Runner material properties.

    Defaults are structural steel. Unlike the beam demo (which used nu=0 to
    match 1-D Euler-Bernoulli theory), a 3-D runner has no analytic reference,
    so the physically correct Poisson ratio nu=0.30 is used.

    Attributes:
        youngs_modulus: Young's modulus in Pa
        density: Material density in kg/m^3
        poisson_ratio: Poisson ratio (dimensionless)
    """
    youngs_modulus: float = 210e9
    density: float = 7850.0
    poisson_ratio: float = 0.30


@dataclass
class BCConfig:
    """Coordinate-region clamp at the runner hub.

    The runner is fixed where it connects to the shaft. Because the dtOO mesh
    lives in non-physical/scaled coordinates with an unknown axis, every value
    here must be set from the axis-discovery diagnostic (see README) rather than
    assumed. This is the runner analogue of ``demo/beam/solver.py`` apply_bc().

    Attributes:
        axis: Rotation axis, one of "x" / "y" / "z"
        hub_center: Center (c1, c2) in the plane perpendicular to the axis
        hub_radius: Clamp nodes whose radial distance from the axis <= this
        axial_min: Optional lower bound of the axial clamp band
        axial_max: Optional upper bound of the axial clamp band
        mode: "radius_band" (radius + optional axial band) or "axial_plane"
        plane_value: Axial coordinate of the clamp plane (mode="axial_plane")
        plane_tol: Tolerance for the axial-plane match
    """
    # NOTE: smoke-test defaults for the T2_7461 mech mesh (bbox z in [0, 2.5]).
    # Clamps the flat z=0 end plane. Physical hub/shaft identification is still
    # TODO -- re-run `python3 mesh_prep.py` and adjust if z=0 is not the hub.
    axis: str = "z"
    hub_center: Tuple[float, float] = (0.0, 0.0)
    hub_radius: float = 0.15
    axial_min: Optional[float] = None
    axial_max: Optional[float] = None
    mode: str = "axial_plane"
    plane_value: float = 0.0
    plane_tol: float = 1e-6


@dataclass
class MeshConfig:
    """Mesh input and volume-meshing fallback options.

    Attributes:
        msh_path: Path to the dtOO-exported .msh (shared data/ directory)
        step_path: Optional STEP/BREP file for the volume-meshing fallback
        force_volume_remesh: Re-mesh to a 3-D volume even if a volume is present
        fallback_element_size: Target element size used by the fallback mesher
        gdim: Geometric dimension passed to the gmsh reader
    """
    msh_path: str = os.path.join(_HERE, "data", "runner.msh")
    step_path: Optional[str] = None
    force_volume_remesh: bool = False
    fallback_element_size: float = 0.05
    gdim: int = 3


@dataclass
class SolverConfig:
    """Modal solver settings.

    freq_min / freq_max are carried for reporting only in step 1 (the forbidden
    frequency band of step 2 is out of scope here).

    Attributes:
        num_eigenvalues: Number of eigenpairs to compute
        tolerance: Eigensolver tolerance
        freq_min: Lower frequency of interest in Hz (reporting only)
        freq_max: Upper frequency of interest in Hz (reporting only)
    """
    num_eigenvalues: int = 10
    tolerance: float = 1e-6
    freq_min: float = 0.0
    freq_max: float = 2000.0
    # Displacement element degree. P1 (=1) keeps the runner mesh (~80k nodes ->
    # ~240k DOFs) within memory; P2 (=2) is ~1M DOFs and OOMs on <8 GB hosts.
    element_degree: int = 1


@dataclass
class DesignConfig:
    """dtOO design parameters exposed to the optimizer.

    `params` maps a dtOO const-value label to (min, max, initial). The labels are
    the cV_* names from the tistos case (see block_structured_meshing/tistos/
    build.py). Default = mid-span blade thickness at LE/mid/TE, which is the most
    direct lever on stiffness+mass and therefore eigenfrequencies.

    Attributes:
        params: {label: (min, max, initial)}
    """
    params: dict = None

    def __post_init__(self):
        if self.params is None:
            self.params = {
                "cV_ru_t_le_a_0.5": (0.005, 0.06, 0.03),
                "cV_ru_t_mid_a_0.5": (0.005, 0.06, 0.03),
                "cV_ru_t_te_a_0.5": (0.005, 0.06, 0.03),
            }

    @property
    def labels(self):
        return list(self.params.keys())

    @property
    def x0(self):
        return [v[2] for v in self.params.values()]

    @property
    def bounds(self):
        return [(v[0], v[1]) for v in self.params.values()]


@dataclass
class OptimizationConfig:
    """Resonance-avoidance optimization settings.

    The forbidden band is computed from the blade-passing frequency
    f_bp = Z_guidevanes * n_rpm / 60 and its harmonics (1× to max_harmonic).

    Attributes:
        Z_guidevanes: Number of guide vanes (determines blade-passing frequency)
        n_rpm: Runner rotational speed in rpm
        max_harmonic: Highest harmonic to check (e.g., 6 covers up to 6×f_bp)
        margin_hz: Minimum half-width of forbidden interval around each harmonic (Hz)
        margin_fraction: Proportional half-width (e.g., 0.05 = 5% of center freq)
        penalty_k: Penalty weight
        max_iter: Maximum optimizer iterations
        method: scipy.optimize.minimize method (gradient-free recommended)
    """
    Z_guidevanes: int = 18
    n_rpm: float = 90.0
    max_harmonic: int = 6
    margin_hz: float = 5.0
    margin_fraction: float = 0.05
    penalty_k: float = 1.0
    max_iter: int = 40
    method: str = "Nelder-Mead"


@dataclass
class DEConfig:
    """Differential Evolution hyperparameters.

    Population-based optimizer; each generation evaluates pop_size designs
    independently -> embarrassingly parallel over workers.

    Environment variables override dataclass defaults (used by run_de.sh):
        DE_POP_SIZE, DE_MAX_GEN, DE_SEED, DE_MUTATION, DE_CROSSOVER, DE_TOL

    Attributes:
        pop_size: Number of individuals per generation (match worker count)
        mutation: Differential weight F (0..2, typically 0.5..1.0)
        crossover: Crossover probability CR (0..1, typically 0.7..0.9)
        max_generations: Maximum generations (total evals = pop_size * max_generations)
        tol: Relative convergence tolerance (stops if std(objectives) < tol)
        seed: Random seed for reproducibility (None = non-reproducible)
    """
    pop_size: int = 20
    mutation: float = 0.8
    crossover: float = 0.9
    max_generations: int = 30
    tol: float = 0.01
    seed: Optional[int] = None

    def __post_init__(self):
        self.pop_size = int(os.environ.get("DE_POP_SIZE", self.pop_size))
        self.max_generations = int(os.environ.get("DE_MAX_GEN", self.max_generations))
        if "DE_SEED" in os.environ:
            self.seed = int(os.environ["DE_SEED"])
        self.mutation = float(os.environ.get("DE_MUTATION", self.mutation))
        self.crossover = float(os.environ.get("DE_CROSSOVER", self.crossover))
        self.tol = float(os.environ.get("DE_TOL", self.tol))


@dataclass
class CFDConfig:
    """Steady-CFD operating point and result-extraction settings.

    The classic hydraulic objectives (efficiency, cavitation volume, design head)
    come from a steady `simpleFoam` run on the dtOO OF case, exactly as in the
    de_framework reference (tistos_files/tistosPyBib.py). Values mirror that
    reference so results are comparable.

    Attributes:
        omega: Runner angular velocity in rad/s (P = moment * omega)
        rho: Fluid density in kg/m^3
        g: Gravitational acceleration in m/s^2
        design_head: Target design head dH_zul in m (head objective = |dH - design_head|)
        operating_point: Postprocessing operating-point key (de_framework uses "n")
        end_time: simpleFoam turbulent-stage endTime (validity = last step == end_time)
    """
    omega: float = 7.53982
    rho: float = 1000.0
    g: float = 9.81
    design_head: float = -2.4
    operating_point: str = "n"
    end_time: int = 500


@dataclass
class ObjectiveConfig:
    """Weights for the combined CFD + resonance objective.

    Scalarized (single-objective) to match the de_framework Differential-Evolution
    setup. The resonance term enters as a constraint/penalty (decision (a)):

        f = w_eta*tanh(eta_term) + w_cav*tanh(Vcav*1e6) + w_head*tanh(head_term)
            + w_resonance * resonance_penalty

    where resonance_penalty = optimization.compute_penalty(freqs, OptimizationConfig).
    Lower is better (minimization). resonance_penalty is 0 unless a mode sits in the
    forbidden band, so it acts as a soft constraint that only bites on violation.

    Attributes:
        w_eta, w_cav, w_head: weights on the three hydraulic objectives
        w_resonance: weight on the resonance penalty (the constraint term)
        mode: "penalty" (soft, additive) or "hard" (large multiplier on violation)
        hard_penalty: multiplier used when mode == "hard"
    """
    w_eta: float = 1.0
    w_cav: float = 1.0
    w_head: float = 1.0
    w_resonance: float = float(os.environ.get("W_RESONANCE", 1.0))
    mode: str = "penalty"
    hard_penalty: float = 1e6


@dataclass
class WetModeConfig:
    """Added-mass / wet-mode settings (DEFERRED — interface only).

    Dry modes are computed now; wet (added-mass) modes are a later extension
    (decision (b)). When `enabled`, the solver also returns wet frequencies and,
    if `compare_dry_wet`, reports dry and wet side by side so the added-mass shift
    can be quantified. A static fluid has no resonance of its own; its only modal
    effect is the inertial added mass that lowers the wet frequencies.

    Attributes:
        enabled: Compute wet (added-mass) modes in addition to dry
        compare_dry_wet: Return/report both dry and wet for comparison
        rho_fluid: Fluid density in kg/m^3 (still water)
        method: "rayleigh" (per-mode level-1) or "matrix" (coupled added-mass)
    """
    enabled: bool = False
    compare_dry_wet: bool = True
    rho_fluid: float = 1000.0
    method: str = "rayleigh"


@dataclass
class OutputConfig:
    """Output options.

    Attributes:
        output_dir: Directory for results
        save_xdmf: Write mesh + mode shapes to XDMF
        results_json: Filename (within output_dir) for the frequency table
    """
    output_dir: str = os.path.join(_HERE, "output")
    save_xdmf: bool = True
    results_json: str = "frequencies.json"
