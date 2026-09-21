"""Configuration dataclasses for hydraulic turbine runner modal analysis.

This module holds only the modal-analysis physics: material, boundary
conditions, mesh input, eigensolver settings, the resonance band definition
and output options. Optimization, CFD and design-parameter concerns live in
the calling framework, not here.
"""

from dataclasses import dataclass, field
from typing import Optional, Tuple


@dataclass
class MaterialConfig:
    """Runner material properties.

    Defaults are structural steel.

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
    """
    Which mesh nodes are fixed (u = 0) before the modal analysis.

    The clamp is a spatial region, not tied to any part label:

    - radius_band: all nodes with radial distance <= hub_radius from
      the rotation axis are fixed.
      axial_min / axial_max (both inclusive, None = unlimited)
      additionally restrict the clamp with AND.
    - axial_plane: all nodes with |axial coordinate - plane_value| <=
      plane_tol.
    - free: nothing fixed; the 6 rigid-body modes are expected and
      discarded.

    The axis and hub region are not known from the mesh itself -- take them
    from the axis-discovery diagnostic (``eigenfrequencies.io.axis``).

    Attributes:
        axis: Rotation axis, one of "x" / "y" / "z"
        hub_center: Axis offset (c1, c2) in the plane perpendicular to the axis
        hub_radius: Fix nodes with radial distance from the axis <= this
            (mode="radius_band")
        axial_min: Optional inclusive lower axial bound (mode="radius_band")
        axial_max: Optional inclusive upper axial bound (mode="radius_band")
        mode: "radius_band" | "axial_plane" | "free"
        plane_value: Axial coordinate of the clamp plane (mode="axial_plane")
        plane_tol: Tolerance for the axial-plane match
    """

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

    When ``msh_path`` is unset the 3-D volume mesh is generated from
    ``step_path`` (gmsh OCC, ``fallback_element_size``) at load time. At least
    one of the two must be provided; ``resolve_msh_path`` raises if neither is
    set.

    Attributes:
        msh_path: Path to the .msh file; optional when ``step_path`` is given
        step_path: Optional STEP/BREP file -- sole mesh source when ``msh_path``
            is unset, fallback for broken/surface-only meshes otherwise
        force_volume_remesh: Re-mesh to a 3-D volume even if a volume is present
        fallback_element_size: Target element size used by the fallback mesher
        gdim: Geometric dimension passed to the gmsh reader
        scale_factor: Uniform scale applied to the mesh coordinates at load time
            (unit conversion from CAD to metres); 1.0 = no scaling
    """

    msh_path: Optional[str] = None
    step_path: Optional[str] = None
    force_volume_remesh: bool = False
    fallback_element_size: float = 0.05
    gdim: int = 3
    scale_factor: float = 1.0


@dataclass
class SolverConfig:
    """Modal solver settings.

    Attributes:
        num_eigenvalues: Number of eigenpairs to compute
        tolerance: Eigensolver tolerance
        freq_min: Lower frequency of interest in Hz (reporting only)
        freq_max: Upper frequency of interest in Hz (reporting only)
        element_degree: Displacement element degree. **Defaults to 2.**
            P1 (=1) is cheaper but overestimates bending-dominated
            eigenfrequencies ~15-20% on thin structures (measured against
            experiment on the test-case (laval disc)).
        solver_backend: "scipy" (eigsh on CSR slices) or "slepc" (PETSc/SLEPc
            shift-invert + MUMPS factorization, scales past ~1M DOFs). Both
            support every BC mode and agree to machine precision on the same
            problem, so this is a choice of numerics, not of physics: pick
            slepc when the factorization is the memory wall. See
            tests/solver/test_backend_equivalence.py.
    """

    num_eigenvalues: int = 10
    tolerance: float = 1e-6
    freq_min: float = 0.0
    freq_max: float = 2000.0
    element_degree: int = 2
    solver_backend: str = "scipy"


@dataclass
class ResonanceConfig:
    """Resonance-avoidance band definition for the penalty.

    The forbidden band is computed from the blade-passing frequency
    f_bp = Z_guidevanes * n_rpm / 60 and its harmonics (1x to max_harmonic).

    Attributes:
        n_rpm: Runner rotational speed in rpm (supplied by the caller)
        Z_guidevanes: Number of guide vanes (determines blade-passing frequency)
        max_harmonic: Highest harmonic to check (e.g., 6 covers up to 6xf_bp)
        margin_hz: Minimum half-width of forbidden interval around each harmonic (Hz)
        margin_fraction: Proportional half-width (e.g., 0.05 = 5% of center freq)
        penalty_k: Penalty weight factor (physics scaling; kept at 1.0)
    """

    n_rpm: float
    Z_guidevanes: int = 18
    max_harmonic: int = 6
    margin_hz: float = 5.0
    margin_fraction: float = 0.05
    penalty_k: float = 1.0


@dataclass
class WetModeConfig:
    """Added-mass / wet-mode settings (DEFERRED -- interface only).

    Dry modes are computed now; wet (added-mass) modes are a later extension.
    When `enabled`, the solver also returns wet frequencies and, if
    `compare_dry_wet`, reports dry and wet side by side so the added-mass shift
    can be quantified. A static fluid has no resonance of its own; its only
    modal effect is the inertial added mass that lowers the wet frequencies.

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

    output_dir: str = "output"
    save_xdmf: bool = True
    results_json: str = "frequencies.json"


@dataclass
class ModalAnalysisConfig:
    """Aggregate configuration for one modal-analysis + penalty evaluation.

    ``resonance`` is required because it carries ``n_rpm`` (no default). All
    other sub-configs fall back to their defaults.
    """

    resonance: ResonanceConfig
    material: MaterialConfig = field(default_factory=MaterialConfig)
    bc: BCConfig = field(default_factory=BCConfig)
    mesh: MeshConfig = field(default_factory=MeshConfig)
    solver: SolverConfig = field(default_factory=SolverConfig)
    wet_mode: WetModeConfig = field(default_factory=WetModeConfig)
    output: OutputConfig = field(default_factory=OutputConfig)
