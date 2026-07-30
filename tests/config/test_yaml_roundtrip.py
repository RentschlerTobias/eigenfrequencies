"""YAML roundtrip tests: load -> dump -> load must produce identical trees.

Also verifies that the three example YAMLs reproduce their golden configs.
"""

import os
import tempfile
from dataclasses import asdict

import pytest

from eigenfrequencies.config import (
    BCConfig,
    CFDConfig,
    DEConfig,
    DesignConfig,
    MaterialConfig,
    MeshConfig,
    ObjectiveConfig,
    OptimizationConfig,
    OutputConfig,
    RunConfig,
    SolverConfig,
    WetModeConfig,
)
from eigenfrequencies.config_yaml import dump_config, load_config

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _deep_eq(a, b):
    """Deep equality that treats tuples and lists as equivalent."""
    if type(a) is not type(b):
        if isinstance(a, (list, tuple)) and isinstance(b, (list, tuple)):
            return len(a) == len(b) and all(_deep_eq(x, y) for x, y in zip(a, b))
        return False
    if isinstance(a, dict):
        return a.keys() == b.keys() and all(_deep_eq(a[k], b[k]) for k in a)
    if isinstance(a, (list, tuple)):
        return len(a) == len(b) and all(_deep_eq(x, y) for x, y in zip(a, b))
    return a == b


# ---------------------------------------------------------------------------
# Example YAML paths
# ---------------------------------------------------------------------------

_REPO_ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
_EXAMPLES_DIR = os.path.join(_REPO_ROOT, "examples", "configs")

_BEAM_YAML = os.path.join(_EXAMPLES_DIR, "beam.yaml")
_TESTCASE_YAML = os.path.join(_EXAMPLES_DIR, "testcase_laval.yaml")
_TISTOS_YAML = os.path.join(_EXAMPLES_DIR, "tistos.yaml")


# ---------------------------------------------------------------------------
# Expected RunConfig instances
# ---------------------------------------------------------------------------

_BEAM_EXPECTED = RunConfig(
    material=MaterialConfig(
        youngs_modulus=210000000000.0,
        density=7850.0,
        poisson_ratio=0.0,
    ),
    bc=BCConfig(
        axis="x",
        hub_center=(0.0, 0.0),
        hub_radius=0.15,
        axial_min=None,
        axial_max=None,
        mode="axial_plane",
        plane_value=0.0,
        plane_tol=1e-6,
    ),
    mesh=MeshConfig(
        msh_path="data/runner.msh",
        step_path=None,
        force_volume_remesh=False,
        fallback_element_size=0.05,
        gdim=3,
    ),
    solver=SolverConfig(
        num_eigenvalues=10,
        tolerance=1e-6,
        freq_min=0.0,
        freq_max=1000.0,
        element_degree=2,
        solver_backend="scipy",
    ),
    design=DesignConfig(params={}),
    optimization=OptimizationConfig(
        n_rpm=72.0,
        Z_guidevanes=18,
        max_harmonic=6,
        margin_hz=5.0,
        margin_fraction=0.05,
        penalty_k=1.0,
        max_iter=40,
        method="Nelder-Mead",
    ),
    de=DEConfig(
        pop_size=20,
        mutation=0.8,
        crossover=0.9,
        max_generations=30,
        tol=0.01,
        seed=None,
    ),
    cfd=CFDConfig(
        n_rpm=72.0,
        omega=7.5398223686155035,
        rho=1000.0,
        g=9.81,
        design_head=-2.4,
        operating_point="n",
        end_time=500,
        post_folder="100",
    ),
    objective=ObjectiveConfig(
        eval_mode="combined",
        w_eta=1.0,
        w_cav=1.0,
        w_head=1.0,
        w_resonance=1.0,
        mode="penalty",
        hard_penalty=1000000.0,
    ),
    wet_mode=WetModeConfig(
        enabled=False,
        compare_dry_wet=True,
        rho_fluid=1000.0,
        method="rayleigh",
    ),
    output=OutputConfig(
        output_dir="output",
        save_xdmf=True,
        results_json="frequencies.json",
    ),
)

_TESTCASE_EXPECTED = RunConfig(
    material=MaterialConfig(
        youngs_modulus=75854000000.0,
        density=8910.0,
        poisson_ratio=0.34,
    ),
    bc=BCConfig(
        axis="z",
        hub_center=(0.0, 0.0),
        hub_radius=0.15,
        axial_min=None,
        axial_max=None,
        mode="free",
        plane_value=0.0,
        plane_tol=1e-6,
    ),
    mesh=MeshConfig(
        msh_path="turbine_runner/data/testcase_coarse.msh",
        step_path=None,
        force_volume_remesh=False,
        fallback_element_size=0.05,
        gdim=3,
    ),
    solver=SolverConfig(
        num_eigenvalues=16,
        tolerance=1e-6,
        freq_min=0.0,
        freq_max=2000.0,
        element_degree=1,
        solver_backend="slepc",
    ),
    design=DesignConfig(params={}),
    optimization=OptimizationConfig(
        n_rpm=72.0,
        Z_guidevanes=18,
        max_harmonic=6,
        margin_hz=5.0,
        margin_fraction=0.05,
        penalty_k=1.0,
        max_iter=40,
        method="Nelder-Mead",
    ),
    de=DEConfig(
        pop_size=20,
        mutation=0.8,
        crossover=0.9,
        max_generations=30,
        tol=0.01,
        seed=None,
    ),
    cfd=CFDConfig(
        n_rpm=72.0,
        omega=7.5398223686155035,
        rho=1000.0,
        g=9.81,
        design_head=-2.4,
        operating_point="n",
        end_time=500,
        post_folder="100",
    ),
    objective=ObjectiveConfig(
        eval_mode="combined",
        w_eta=1.0,
        w_cav=1.0,
        w_head=1.0,
        w_resonance=1.0,
        mode="penalty",
        hard_penalty=1000000.0,
    ),
    wet_mode=WetModeConfig(
        enabled=False,
        compare_dry_wet=True,
        rho_fluid=1000.0,
        method="rayleigh",
    ),
    output=OutputConfig(
        output_dir="output",
        save_xdmf=True,
        results_json="frequencies.json",
    ),
)


def _tistos_expected():
    """Build the tistos RunConfig from the golden JSON values."""
    import json

    golden_path = os.path.join(
        os.path.dirname(__file__), "..", "characterization", "golden", "config_roundtrip.json"
    )
    with open(golden_path) as fh:
        golden = json.load(fh)

    return RunConfig(
        material=MaterialConfig(**golden["MaterialConfig"]),
        bc=BCConfig(**golden["BCConfig"]),
        mesh=MeshConfig(**golden["MeshConfig"]),
        solver=SolverConfig(**golden["SolverConfig"]),
        design=DesignConfig(params=golden["DesignConfig"]["params"]),
        optimization=OptimizationConfig(**golden["OptimizationConfig"]),
        de=DEConfig(**golden["DEConfig"]),
        cfd=CFDConfig(**golden["CFDConfig"]),
        objective=ObjectiveConfig(**golden["ObjectiveConfig"]),
        wet_mode=WetModeConfig(**golden["WetModeConfig"]),
        output=OutputConfig(**golden["OutputConfig"]),
    )


# ---------------------------------------------------------------------------
# Roundtrip tests
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("yaml_path,expected", [
    (_BEAM_YAML, _BEAM_EXPECTED),
    (_TESTCASE_YAML, _TESTCASE_EXPECTED),
    (_TISTOS_YAML, _tistos_expected()),
])
def test_yaml_load_matches_expected(yaml_path, expected):
    """Loading an example YAML must produce the expected RunConfig tree."""
    loaded = load_config(yaml_path)
    assert _deep_eq(asdict(loaded), asdict(expected)), (
        f"Loaded config from {yaml_path} does not match expected tree"
    )


@pytest.mark.parametrize("yaml_path", [_BEAM_YAML, _TESTCASE_YAML, _TISTOS_YAML])
def test_yaml_roundtrip_stability(yaml_path):
    """load -> dump -> load must yield an identical dataclass tree."""
    first = load_config(yaml_path)

    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as tmp:
        tmp_path = tmp.name

    try:
        dump_config(first, tmp_path)
        second = load_config(tmp_path)
    finally:
        os.unlink(tmp_path)

    assert _deep_eq(asdict(first), asdict(second)), (
        f"Roundtrip diverged for {yaml_path}"
    )
