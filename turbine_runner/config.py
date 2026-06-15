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

    Penalty pushes every eigenfrequency out of the forbidden band [f_min, f_max].

    Attributes:
        f_min: Lower bound of the forbidden frequency band in Hz
        f_max: Upper bound of the forbidden frequency band in Hz
        penalty_k: Penalty weight
        margin: Extra safety margin (Hz) added around the band
        max_iter: Maximum optimizer iterations
        method: scipy.optimize.minimize method (gradient-free recommended)
    """
    f_min: float = 100.0
    f_max: float = 150.0
    penalty_k: float = 1.0
    margin: float = 0.0
    max_iter: int = 40
    method: str = "Nelder-Mead"


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
