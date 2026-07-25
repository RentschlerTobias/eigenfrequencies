"""Configuration for hydraulic turbine runner modal analysis.

Mirrors the dataclass style of ``demo/beam/config.py`` but targets an externally
generated runner mesh (from dtOO) instead of a parametric beam.
"""

import math
import os
from dataclasses import dataclass
from typing import Optional, Tuple


_HERE = os.path.dirname(os.path.abspath(__file__))


def _load_n_rpm_from_template() -> float:
    """Read cV_n (rpm) from templateState.xml — single source of truth for the CFD operating point."""
    import xml.etree.ElementTree as ET

    template_path = os.path.join(_HERE, "cfd", "tistos_files", "templateState.xml")
    tree = ET.parse(template_path)
    for cv in tree.iter("constValue"):
        if cv.get("label") == "cV_n":
            return float(cv.get("value"))
    raise RuntimeError(f"cV_n not found in {template_path}")


# cV_n in templateState.xml drives MRFProperties omega = 2*pi*n/60. N_RPM env overrides.
_N_RPM_DEFAULT = float(os.environ.get("N_RPM") or _load_n_rpm_from_template())


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
        mode: "radius_band" (radius + optional axial band), "axial_plane",
            or "free" (no clamp at all; free-free vibration for experimental
            validation -- the 6 rigid-body modes are expected and discarded)
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
        element_degree: Displacement element degree. P1 (=1) keeps the runner
            mesh (~80k nodes -> ~240k DOFs) within memory but overestimates
            bending-dominated eigenfrequencies ~15-20% on thin structures
            (measured against experiment on the test-case disc); use 2
            (quadratic, ~1M DOFs, needs ~8 GB+) for validation-grade runs.
        solver_backend: "scipy" (eigsh on CSR slices, suited to clamped BCs)
            or "slepc" (PETSc/SLEPc shift-invert + MUMPS factorization;
            free-free mode only, scales past ~1M DOFs).
    """
    num_eigenvalues: int = 10
    tolerance: float = 1e-6
    freq_min: float = 0.0
    freq_max: float = 2000.0
    element_degree: int = 1
    solver_backend: str = "scipy"


_DESIGN_PRESETS = {
    # mid-span blade thickness at LE/mid/TE: most direct lever on stiffness+mass
    # and therefore eigenfrequencies. Cheap smoke-test dimensionality.
    "t_midspan3": {
        "cV_ru_t_le_a_0.5": (0.005, 0.06, 0.03),
        "cV_ru_t_mid_a_0.5": (0.005, 0.06, 0.03),
        "cV_ru_t_te_a_0.5": (0.005, 0.06, 0.03),
    },
    # Bounds from de_framework tistosRunner.DoF — NOT templateState.xml slider ranges (those produce degenerate geometry).
    "full30": {
        "cV_ru_alpha_1_ex_0.0": (-0.155, 0.025, 0.004872982423868022),
        "cV_ru_alpha_1_ex_0.5": (-0.19, -0.01, -0.11506513546824179),
        "cV_ru_alpha_1_ex_1.0": (-0.19, -0.01, -0.015079716192407971),
        "cV_ru_alpha_2_ex_0.0": (-0.08, 0.1, 0.03402273030531863),
        "cV_ru_alpha_2_ex_0.5": (-0.08, 0.1, 0.03875801072398795),
        "cV_ru_alpha_2_ex_1.0": (-0.08, 0.07, -0.06818810955839917),
        "cV_ru_offsetM_ex_0.0": (1.0, 1.5, 1.4337715415968637),
        "cV_ru_offsetM_ex_0.5": (1.0, 1.5, 1.3086522283750657),
        "cV_ru_offsetM_ex_1.0": (1.0, 1.5, 1.3286597825110331),
        "cV_ru_ratio_0.0": (0.4, 0.6, 0.5155095255375718),
        "cV_ru_ratio_0.5": (0.4, 0.6, 0.40202440411861723),
        "cV_ru_ratio_1.0": (0.4, 0.6, 0.5354515688199649),
        "cV_ru_offsetPhiR_ex_0.0": (-0.15, 0.15, 0.04571841251056208),
        "cV_ru_offsetPhiR_ex_0.5": (-0.15, 0.15, -0.0026510870865109615),
        "cV_ru_offsetPhiR_ex_1.0": (-0.15, 0.15, 0.04602043523346666),
        "cV_ru_bladeLength_0.0": (0.4, 0.8, 0.40400214390547823),
        "cV_ru_bladeLength_0.5": (0.6, 1.0, 0.6833682636796429),
        "cV_ru_bladeLength_1.0": (0.8, 1.3, 1.098288373885862),
        "cV_ru_t_le_a_0": (0.005, 0.06, 0.04333963143275606),
        "cV_ru_t_le_a_0.5": (0.005, 0.06, 0.05970486035898813),
        "cV_ru_t_le_a_1": (0.005, 0.06, 0.027243502852337103),
        "cV_ru_t_mid_a_0": (0.005, 0.06, 0.014698095985221829),
        "cV_ru_t_mid_a_0.5": (0.005, 0.06, 0.028962957830934426),
        "cV_ru_t_mid_a_1": (0.005, 0.06, 0.04796504902806092),
        "cV_ru_t_te_a_0": (0.005, 0.06, 0.01577708084197574),
        "cV_ru_t_te_a_0.5": (0.005, 0.06, 0.01945021940488333),
        "cV_ru_t_te_a_1": (0.005, 0.06, 0.009023193367017956),
        "cV_ru_u_mid_a_0": (0.4, 0.6, 0.42832406190006633),
        "cV_ru_u_mid_a_0.5": (0.4, 0.6, 0.41227246166708625),
        "cV_ru_u_mid_a_1": (0.4, 0.6, 0.46713946749249541),
    },
}


@dataclass
class DesignConfig:
    """dtOO design parameters exposed to the optimizer.

    `params` maps a dtOO const-value label to (min, max, initial). The labels are
    the cV_* names from the tistos case (see block_structured_meshing/tistos/
    build.py). Preset selectable via env DESIGN_PRESET (default "full30",
    alternative "t_midspan3"); see _DESIGN_PRESETS.

    Attributes:
        params: {label: (min, max, initial)}
    """
    params: dict = None

    def __post_init__(self):
        if self.params is None:
            preset = os.environ.get("DESIGN_PRESET", "full30")
            if preset not in _DESIGN_PRESETS:
                raise ValueError(
                    f"DESIGN_PRESET must be one of {tuple(_DESIGN_PRESETS)}, got {preset!r}"
                )
            self.params = dict(_DESIGN_PRESETS[preset])

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
        n_rpm: Runner rotational speed in rpm (from cV_n in templateState.xml;
            N_RPM env overrides for parametric studies)
        max_harmonic: Highest harmonic to check (e.g., 6 covers up to 6×f_bp)
        margin_hz: Minimum half-width of forbidden interval around each harmonic (Hz)
        margin_fraction: Proportional half-width (e.g., 0.05 = 5% of center freq)
        penalty_k: Penalty weight
        max_iter: Maximum optimizer iterations
        method: scipy.optimize.minimize method (gradient-free recommended)
    """
    Z_guidevanes: int = 18
    n_rpm: float = _N_RPM_DEFAULT
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
        omega: Runner angular velocity in rad/s (P = moment * omega);
            derived as 2*pi*n_rpm/60 from the same cV_n source
        rho: Fluid density in kg/m^3
        g: Gravitational acceleration in m/s^2
        design_head: Target design head dH_zul in m (head objective = |dH - design_head|)
        operating_point: Postprocessing operating-point key (de_framework uses "n")
        end_time: simpleFoam turbulent-stage endTime (validity = last step == end_time)
    """
    omega: float = 2.0 * math.pi * _N_RPM_DEFAULT / 60.0
    rho: float = 1000.0
    g: float = 9.81
    design_head: float = -2.4
    operating_point: str = "n"
    end_time: int = 500
    # postProcessing/<fo>/<post_folder>: the turbulent restart writes into the
    # folder named by its start time (laminar endTime = 100), so results live in
    # "100" and the last row is the turbulent endTime. Matches de_framework.
    post_folder: str = "100"


@dataclass
class ObjectiveConfig:
    """Weights + evaluation mode for the CFD + resonance objective.

    Scalarized (single-objective) to match the de_framework Differential-Evolution
    setup. The resonance term enters as a constraint/penalty (decision (a)):

        f = w_eta*tanh(eta_term) + w_cav*tanh(Vcav*1e6) + w_head*tanh(head_term)
            + w_resonance * resonance_penalty

    where resonance_penalty = optimization.compute_penalty(freqs, OptimizationConfig).
    Lower is better (minimization). resonance_penalty is 0 unless a mode sits in the
    forbidden band, so it acts as a soft constraint that only bites on violation.

    Attributes:
        eval_mode: Which physics runs per evaluation. One of
            - "combined"     : dtOO + CFD (simpleFoam) + dtOO + FEniCSx modal,
                               objective = cfd_scalar + w_resonance*resonance_term
            - "cfd_only"     : dtOO + CFD only, objective = cfd_scalar
            - "resonance_only": dtOO + FEniCSx only, objective = resonance_term
          Env override: EVAL_MODE.
        w_eta, w_cav, w_head: weights on the three hydraulic objectives
        w_resonance: weight on the resonance penalty (the constraint term)
        mode: "penalty" (soft, additive) or "hard" (large multiplier on violation)
        hard_penalty: multiplier used when mode == "hard"
    """
    eval_mode: str = "combined"
    w_eta: float = 1.0
    w_cav: float = 1.0
    w_head: float = 1.0
    w_resonance: float = float(os.environ.get("W_RESONANCE", 1.0))
    mode: str = "penalty"
    hard_penalty: float = 1e6

    def __post_init__(self):
        self.eval_mode = os.environ.get("EVAL_MODE", self.eval_mode)
        valid = ("combined", "cfd_only", "resonance_only")
        if self.eval_mode not in valid:
            raise ValueError(
                f"EVAL_MODE must be one of {valid}, got {self.eval_mode!r}"
            )


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
