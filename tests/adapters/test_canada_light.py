"""Validation tests for the ``canadaLight`` machine adapter.

* YAML loads via ``load_machine_yaml()`` and produces a valid ``DtooAdapter``.
* ``bc()`` returns a ``free_free`` BCConfig (task requirement).
* ``design_bounds()`` exposes 21 spanwise runner-blade parameters.
* ``export_mesh()`` delegates to ``run_dtoo_export`` (mocked locally).
* Free-free modal solve: 6 rigid-body modes ~ 0 Hz, elastic freqs plausible.

Pure-Python tests (YAML, adapter, mocked export) run locally without dtOO.
The free-free solve test skips when dtOO or dolfinx are unavailable — it
requires the dtOO + FEniCSx container stack.
"""

import importlib.util
import os
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
_MACHINE_YAML = _REPO_ROOT / "adapters" / "machines" / "canadaLight.yaml"

# ---------------------------------------------------------------------------
# Availability guards (per-class, not module-level)
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

class TestCanadaLightYaml:
    """YAML must load and produce a valid ``MachineAdapterConfig``."""

    def test_yaml_loads(self):
        cfg = load_machine_yaml(_MACHINE_YAML)
        assert cfg.name == "canadaLight"
        assert cfg.state == "E1_12685"
        assert cfg.mech_volume == "ruWithRounding_mechMesh"
        assert cfg.adjust_plugin == "ru_adjustDomain"
        assert cfg.mesh_scale_factor == 1.0
        assert cfg.bc_template == BCTemplate("free_free")
        assert cfg.axis == "auto"

    def test_design_has_21_parameters(self):
        cfg = load_machine_yaml(_MACHINE_YAML)
        assert len(cfg.design) == 21

    def test_design_bounds_valid(self):
        cfg = load_machine_yaml(_MACHINE_YAML)
        for label, bounds in cfg.design.items():
            assert bounds.min <= bounds.max, f"{label}: min > max"
            assert label.startswith("cV_ru_"), f"unexpected label: {label}"

    def test_spanwise_sections_present(self):
        cfg = load_machine_yaml(_MACHINE_YAML)
        names = set(cfg.design.keys())
        for section in ("0.0", "0.5", "1.0"):
            assert f"cV_ru_bladeLength_{section}" in names
            assert f"cV_ru_alpha_1_ex_{section}" in names


# ---------------------------------------------------------------------------
# Adapter (no container needed)
# ---------------------------------------------------------------------------

class TestCanadaLightAdapter:
    """``DtooAdapter`` wrapping the canadaLight YAML."""

    def test_adapter_creates(self):
        adapter = DtooAdapter(_MACHINE_YAML)
        assert adapter.config.name == "canadaLight"

    def test_bc_returns_free_free(self):
        adapter = DtooAdapter(_MACHINE_YAML)
        bc = adapter.bc()
        assert isinstance(bc, BCConfig)
        assert bc.mode == "free"

    def test_design_bounds(self):
        adapter = DtooAdapter(_MACHINE_YAML)
        bounds = adapter.design_bounds()
        assert len(bounds) == 21
        for label, (lo, hi) in bounds.items():
            assert lo <= hi, f"{label}: min > max"
            assert label.startswith("cV_ru_")

    def test_axis_auto(self):
        adapter = DtooAdapter(_MACHINE_YAML)
        assert adapter.axis == "auto"


# ---------------------------------------------------------------------------
# export_mesh (mocked — no container)
# ---------------------------------------------------------------------------

class TestCanadaLightExportMocked:
    """``export_mesh`` delegation tested via mocking (no dtOO required)."""

    def test_export_mesh_calls_run_dtoo_export(self):
        adapter = DtooAdapter(_MACHINE_YAML)
        design = {"cV_ru_bladeLength_0.5": 0.69}

        with patch(
            "eigenfrequencies.adapters.dtoo.export.run_dtoo_export",
            return_value="/tmp/canadaLight_export.msh",
        ) as mock_export:
            result = adapter.export_mesh(design)

        mock_export.assert_called_once()
        assert result == "/tmp/canadaLight_export.msh"
        call_args = mock_export.call_args
        assert call_args.args[0] == adapter.config
        assert call_args.args[1] == design


# ---------------------------------------------------------------------------
# Free-free solve (requires dtOO + dolfinx — container only)
# ---------------------------------------------------------------------------

@requires_full_stack
class TestCanadaLightFreeFreeSolve:
    """Free-free modal solve: export mesh from dtOO, solve with SLEPc, verify
    6 rigid-body modes ~ 0 Hz and elastic frequencies in a plausible range."""

    def test_free_free_solve_rigid_modes_and_elastic(self, tmp_path: Path):
        """Export the baseline canadaLight mesh (no design overrides) and
        run a free-free eigenanalysis.  Sanity check: at least 6 rigid-body
        modes below 1 Hz, and at least 4 elastic frequencies above 1 Hz
        but below some physically plausible ceiling.

        Given: canadaLight adapter with free_free BC.
        When: export mesh + free-free SLEPc solve.
        Then: 6 rigid modes ~ 0 Hz, first elastic freqs plausible.
        """
        from eigenfrequencies.adapters.dtoo.export import run_dtoo_export
        from eigenfrequencies.config import (
            MaterialConfig,
            OutputConfig,
            SolverConfig,
        )
        from eigenfrequencies.io.load import load_and_prepare_mesh
        from eigenfrequencies.solver.core import ModalSolver

        # 1. Export mesh from canadaLight baseline.
        adapter = DtooAdapter(_MACHINE_YAML)
        output_msh = str(tmp_path / "canadaLight_baseline.msh")
        mesh_path = run_dtoo_export(adapter.config, {}, output_msh)
        assert os.path.isfile(mesh_path), f"mesh not exported: {mesh_path}"

        # 2. Load mesh + solve free-free.
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
        assert len(freqs_hz) >= 10, f"expected >=10 eigenpairs, got {len(freqs_hz)}"

        # Rigid-body modes: first 6 should be below 1 Hz.
        rigid = [f for f in freqs_hz if f < 1.0]
        assert len(rigid) >= 6, (
            f"expected >=6 rigid-body modes < 1 Hz, got {len(rigid)}: "
            f"freqs = {[f'{f:.2f}' for f in freqs_hz[:10]]}"
        )

        # Elastic modes: at least 4 above 1 Hz but below a plausible ceiling
        # (a small Kaplan-like runner should have its first elastic modes
        #  in the 50-500 Hz range; much higher would be suspicious).
        elastic = [f for f in freqs_hz if 1.0 <= f <= 2000.0]
        assert len(elastic) >= 4, (
            f"expected >=4 elastic modes in [1, 2000] Hz, got {len(elastic)}: "
            f"elastic freqs = {[f'{f:.2f}' for f in elastic]}"
        )

        # First elastic frequency should be well above rigid modes.
        assert elastic[0] > 10.0, (
            f"first elastic freq {elastic[0]:.2f} Hz too close to rigid modes"
        )
