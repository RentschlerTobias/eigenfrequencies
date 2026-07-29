"""Validation tests for the ``naca`` machine adapter.

* YAML loads via ``load_machine_yaml()`` and produces a valid ``DtooAdapter``.
* ``bc()`` returns an ``axial_plane`` BCConfig (foil-root clamp).
* ``design_bounds()`` exposes 7 foil-blade profile parameters (no spanwise sections).
* ``export_mesh()`` delegates to ``run_dtoo_export`` (mocked locally).
* Foil-clamp modal solve: 2–3 constrained rigid-body modes near 0 Hz (rotation
  about x / y axes), elastic freqs plausible for a thin NACA00xx foil.

Pure-Python tests (YAML, adapter, mocked export) run locally without dtOO.
The foil-clamp solve test skips when dtOO or dolfinx are unavailable — it
requires the dtOO + FEniCSx container stack.
"""

import importlib.util
from pathlib import Path
from unittest.mock import patch

import pytest

from eigenfrequencies.adapters.dtoo.adapter import DtooAdapter
from eigenfrequencies.adapters.dtoo.machine_yaml import (
    BCTemplate,
    load_machine_yaml,
)
from eigenfrequencies.config import BCConfig

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_MACHINE_YAML = _REPO_ROOT / "adapters" / "machines" / "naca.yaml"

# ---------------------------------------------------------------------------
# Availability guards
# ---------------------------------------------------------------------------

_DTOO_AVAILABLE = importlib.util.find_spec("dtOOPythonSWIG") is not None
_DOLFINX_AVAILABLE = importlib.util.find_spec("dolfinx") is not None

requires_dtoo = pytest.mark.skipif(
    not _DTOO_AVAILABLE,
    reason="dtOOPythonSWIG not available — requires dtOO container",
)
requires_full_stack = pytest.mark.skipif(
    not (_DTOO_AVAILABLE and _DOLFINX_AVAILABLE),
    reason="dtOO + dolfinx required — run with both dtOO and FEniCSx available",
)


# ---------------------------------------------------------------------------
# YAML parsing (no container needed)
# ---------------------------------------------------------------------------

class TestNacaYaml:
    """YAML must load and produce a valid ``MachineAdapterConfig``."""

    def test_yaml_loads(self):
        cfg = load_machine_yaml(_MACHINE_YAML)
        assert cfg.name == "naca"
        assert cfg.state == "init"
        assert cfg.mech_volume == "gridGmsh"
        assert cfg.adjust_plugin == ""
        assert cfg.mesh_scale_factor == 1.0
        assert cfg.bc_template == BCTemplate("foil_clamp")
        assert cfg.axis == "auto"

    def test_design_has_7_parameters(self):
        cfg = load_machine_yaml(_MACHINE_YAML)
        assert len(cfg.design) == 7

    def test_design_bounds_valid(self):
        cfg = load_machine_yaml(_MACHINE_YAML)
        for label, bounds in cfg.design.items():
            assert bounds.min <= bounds.max, f"{label}: min > max"
            assert label.startswith("cV_"), f"unexpected label: {label}"

    def test_foil_profile_params_present(self):
        cfg = load_machine_yaml(_MACHINE_YAML)
        names = set(cfg.design.keys())
        assert "cV_alpha_1_ex" in names
        assert "cV_alpha_2_ex" in names
        assert "cV_M_ex" in names
        assert "cV_offsetM_ex" in names
        assert "cV_offsetPhiR_ex" in names
        assert "cV_ratio" in names
        assert "cV_bladeLength" in names


# ---------------------------------------------------------------------------
# Adapter (no container needed)
# ---------------------------------------------------------------------------

class TestNacaAdapter:
    """``DtooAdapter`` wrapping the naca YAML."""

    def test_adapter_creates(self):
        adapter = DtooAdapter(_MACHINE_YAML)
        assert adapter.config.name == "naca"

    def test_bc_returns_foil_clamp(self):
        adapter = DtooAdapter(_MACHINE_YAML)
        bc = adapter.bc()
        assert isinstance(bc, BCConfig)
        assert bc.mode == "axial_plane"

    def test_design_bounds(self):
        adapter = DtooAdapter(_MACHINE_YAML)
        bounds = adapter.design_bounds()
        assert len(bounds) == 7
        for label, (lo, hi) in bounds.items():
            assert lo <= hi, f"{label}: min > max"
            assert label.startswith("cV_")

    def test_axis_auto(self):
        adapter = DtooAdapter(_MACHINE_YAML)
        assert adapter.axis == "auto"


# ---------------------------------------------------------------------------
# export_mesh (mocked — no container)
# ---------------------------------------------------------------------------

class TestNacaExportMocked:
    """``export_mesh`` delegation tested via mocking (no dtOO required)."""

    def test_export_mesh_calls_run_dtoo_export(self):
        adapter = DtooAdapter(_MACHINE_YAML)
        design = {"cV_bladeLength": 0.7}

        with patch(
            "eigenfrequencies.adapters.dtoo.export.run_dtoo_export",
            return_value="/tmp/naca_export.msh",
        ) as mock_export:
            result = adapter.export_mesh(design)

        mock_export.assert_called_once()
        assert result == "/tmp/naca_export.msh"
        call_args = mock_export.call_args
        assert call_args.args[0] == adapter.config
        assert call_args.args[1] == design


# ---------------------------------------------------------------------------
# Foil-clamp solve (requires dtOO + dolfinx — container only)
# ---------------------------------------------------------------------------

@requires_full_stack
class TestNacaFoilClampSolve:
    """Foil-clamp modal solve: export mesh from dtOO, solve with SLEPc, verify
    2–3 constrained rigid-body modes near 0 Hz (rotation about x / y axes) and
    elastic frequencies in a plausible range for a thin NACA00xx foil.

    Given: naca adapter with foil_clamp BC (axial-plane clamp at z=0).
    When: export mesh + foil-clamp SLEPc solve.
    Then: 2–3 constrained rigid modes ~ 0 Hz, first elastic freqs plausible.
    """

    def test_foil_clamp_solve_rigid_and_elastic(self, tmp_path: Path):
        from eigenfrequencies.adapters.dtoo.export import run_dtoo_export
        from eigenfrequencies.config import (
            MaterialConfig,
            OutputConfig,
            SolverConfig,
        )
        from eigenfrequencies.io.load import load_and_prepare_mesh
        from eigenfrequencies.solver.core import ModalSolver

        # 1. Export mesh from naca baseline.
        adapter = DtooAdapter(_MACHINE_YAML)
        output_msh = str(tmp_path / "naca_baseline.msh")
        mesh_path = run_dtoo_export(adapter.config, {}, output_msh)

        # 2. Load mesh + solve with foil-clamp.
        mesh, ct, ft = load_and_prepare_mesh(mesh_path)
        solver = ModalSolver(
            mesh=mesh,
            cell_tags=ct,
            facet_tags=ft,
            bc=adapter.bc(),
            material=MaterialConfig(),
            solver=SolverConfig(
                num_eigenvalues=20,
                solver_backend="slepc",
                freq_min=0.0,
            ),
            output=OutputConfig(output_dir=str(tmp_path / "output")),
        )
        freqs_hz, _ = solver.solve()

        # 3. Sanity checks.
        assert len(freqs_hz) >= 6, f"expected >=6 eigenpairs, got {len(freqs_hz)}"

        # Constrained rigid-body modes: 2–3 should be below 1 Hz (rotation
        # about x and y axes; z-translation is constrained by foil_clamp).
        rigid = [f for f in freqs_hz if f < 1.0]
        assert len(rigid) >= 2, (
            f"expected >=2 constrained rigid-body modes < 1 Hz, got {len(rigid)}: "
            f"freqs = {[f'{f:.2f}' for f in freqs_hz[:10]]}"
        )

        # Elastic modes: at least 3 above 1 Hz but below a plausible ceiling
        # (a thin NACA00xx foil should have its first elastic modes in the
        # 100–2000 Hz range; much higher would be suspicious).
        elastic = [f for f in freqs_hz if 1.0 <= f <= 2000.0]
        assert len(elastic) >= 3, (
            f"expected >=3 elastic modes in [1, 2000] Hz, got {len(elastic)}: "
            f"elastic freqs = {[f'{f:.2f}' for f in elastic]}"
        )

        # First elastic frequency should be well above rigid modes.
        assert elastic[0] > 10.0, (
            f"first elastic freq {elastic[0]:.2f} Hz too close to rigid modes"
        )
