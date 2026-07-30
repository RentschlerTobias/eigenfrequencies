"""Parity validation tests for the tistos machine YAML adapter.

These tests verify that:
1. ``adapters/machines/tistos.yaml`` loads correctly via ``load_machine_yaml()``
   and reproduces the current ``turbine_runner/dtoo_export.py`` tistos setup.
2. Design bounds match the "full30" preset from ``src/eigenfrequencies/config.py``.
3. When dtOO is available (inside ``atismer/dtoo-opensuse:stable`` container):
   - the exported mesh checksum matches the golden reference, and
   - the solver frequencies match the golden tistos-coarse reference
     within 1e-4 relative error and MAC >= 0.999.

Generate the golden solver reference inside the dtOO container by running::

    cd /dtOO/test/tistos
    export LD_LIBRARY_PATH=/dtOO-install/lib:/dtOO-install/lib64
    python3.12 -c "
    from dtOOPythonSWIG import *
    import hashlib, json
    from eigenfrequencies.adapters.dtoo import DtooAdapter
    adapter = DtooAdapter('/workspace/adapters/machines/tistos.yaml')
    mesh_path = adapter.export_mesh({})
    with open(mesh_path, 'rb') as f:
        mesh_hash = hashlib.sha256(f.read()).hexdigest()
    # Solve
    from eigenfrequencies.config import MaterialConfig, SolverConfig
    from eigenfrequencies.io import load_and_prepare_mesh
    domain = load_and_prepare_mesh(adapter.bc())
    solver = ModalSolver(domain, MaterialConfig(), adapter.bc(), SolverConfig(num_eigenvalues=10))
    eigenvalues, eigenvectors = solver.solve()
    import numpy as np
    mode_shapes = [np.linalg.norm(ev.reshape(-1, 3), axis=1) for ev in eigenvectors]
    freqs = solver.compute_frequencies(eigenvalues)
    # Print JSON to copy into golden
    print(json.dumps({'mesh_hash': mesh_hash, 'frequencies': freqs.tolist(),
                      'mode_shapes': [s.tolist() for s in mode_shapes]}, indent=2))
    "
"""

import hashlib
import importlib.util
import json
import os
import tempfile
from pathlib import Path

import numpy as np
import pytest

from eigenfrequencies.adapters.dtoo import DtooAdapter, load_machine_yaml

# Module-level skip: dtOO is only available inside its container.
_DTOO_AVAILABLE = importlib.util.find_spec("dtOOPythonSWIG") is not None

_REPO_ROOT = Path(__file__).resolve().parents[3]
_ADAPTER_YAML = _REPO_ROOT / "adapters" / "machines" / "tistos.yaml"
_GOLDEN_PATH = (
    Path(__file__).resolve().parents[1] / "characterization" / "golden" / "tistos_coarse.json"
)

_FREQ_REL_TOL = 1e-4
_MAC_MIN = 0.999


# ----------------------------------------------------------------------
# Design bounds from the "full30" preset (src/eigenfrequencies/config.py).
# ----------------------------------------------------------------------
_FULL30_BOUNDS = {
    "cV_ru_alpha_1_ex_0.0":    (-0.155,  0.025),
    "cV_ru_alpha_1_ex_0.5":    (-0.19,  -0.01),
    "cV_ru_alpha_1_ex_1.0":    (-0.19,  -0.01),
    "cV_ru_alpha_2_ex_0.0":    (-0.08,   0.1),
    "cV_ru_alpha_2_ex_0.5":    (-0.08,   0.1),
    "cV_ru_alpha_2_ex_1.0":    (-0.08,   0.07),
    "cV_ru_offsetM_ex_0.0":     ( 1.0,    1.5),
    "cV_ru_offsetM_ex_0.5":    ( 1.0,    1.5),
    "cV_ru_offsetM_ex_1.0":    ( 1.0,    1.5),
    "cV_ru_ratio_0.0":         ( 0.4,    0.6),
    "cV_ru_ratio_0.5":         ( 0.4,    0.6),
    "cV_ru_ratio_1.0":         ( 0.4,    0.6),
    "cV_ru_offsetPhiR_ex_0.0": (-0.15,   0.15),
    "cV_ru_offsetPhiR_ex_0.5": (-0.15,   0.15),
    "cV_ru_offsetPhiR_ex_1.0": (-0.15,   0.15),
    "cV_ru_bladeLength_0.0":   ( 0.4,    0.8),
    "cV_ru_bladeLength_0.5":   ( 0.6,    1.0),
    "cV_ru_bladeLength_1.0":   ( 0.8,    1.3),
    "cV_ru_t_le_a_0":          ( 0.005,  0.06),
    "cV_ru_t_le_a_0.5":        ( 0.005,  0.06),
    "cV_ru_t_le_a_1":          ( 0.005,  0.06),
    "cV_ru_t_mid_a_0":         ( 0.005,  0.06),
    "cV_ru_t_mid_a_0.5":       ( 0.005,  0.06),
    "cV_ru_t_mid_a_1":         ( 0.005,  0.06),
    "cV_ru_t_te_a_0":          ( 0.005,  0.06),
    "cV_ru_t_te_a_0.5":        ( 0.005,  0.06),
    "cV_ru_t_te_a_1":          ( 0.005,  0.06),
    "cV_ru_u_mid_a_0":         ( 0.4,    0.6),
    "cV_ru_u_mid_a_0.5":       ( 0.4,    0.6),
    "cV_ru_u_mid_a_1":         ( 0.4,    0.6),
}


def _sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def _compute_mac(mode_a, mode_b):
    """Modal Assurance Criterion between two displacement-norm vectors."""
    a = np.asarray(mode_a)
    b = np.asarray(mode_b)
    num = np.abs(np.dot(a, b)) ** 2
    denom = np.dot(a, a) * np.dot(b, b)
    if denom == 0:
        return 0.0
    return float(num / denom)


# ----------------------------------------------------------------------
# YAML loading and structural tests (always run — no dtOO required).
# ----------------------------------------------------------------------

class TestTistosYamlLoads:
    """Verify the machine YAML parses and reproduces the tistos setup."""

    def test_yaml_file_exists(self):
        assert _ADAPTER_YAML.exists(), f"tistos.yaml not found at {_ADAPTER_YAML}"

    def test_load_machine_yaml_succeeds(self):
        """load_machine_yaml() returns a MachineAdapterConfig without raising."""
        cfg = load_machine_yaml(_ADAPTER_YAML)
        assert cfg.name == "tistos"

    def test_dtoo_settings_match_driver_defaults(self):
        """case_dir, state, mech_volume, adjust_plugin match turbine_runner/dtoo_export.py."""
        cfg = load_machine_yaml(_ADAPTER_YAML)
        assert cfg.case_dir == os.path.expanduser("~/dtOO/build/test/tistos")
        assert cfg.state == "templateState"
        assert cfg.mech_volume == "ruWithRounding_mechMesh"
        assert cfg.adjust_plugin == "ru_adjustDomain"

    def test_all_30_design_bounds_present(self):
        """All 30 full30 preset parameters appear in the YAML design section."""
        cfg = load_machine_yaml(_ADAPTER_YAML)
        assert set(cfg.design.keys()) == set(_FULL30_BOUNDS.keys()), (
            f"Design parameter mismatch.\n"
            f"  YAML labels:   {sorted(cfg.design.keys())}\n"
            f"  Expected:      {sorted(_FULL30_BOUNDS.keys())}\n"
            f"  Missing:       {sorted(set(_FULL30_BOUNDS.keys()) - set(cfg.design.keys()))}\n"
            f"  Extra:         {sorted(set(cfg.design.keys()) - set(_FULL30_BOUNDS.keys()))}"
        )

    def test_design_bounds_match_full30_preset(self):
        """Each design-parameter bound exactly matches the full30 preset."""
        cfg = load_machine_yaml(_ADAPTER_YAML)
        for label, (exp_min, exp_max) in _FULL30_BOUNDS.items():
            actual = cfg.design[label]
            assert actual.min == exp_min and actual.max == exp_max, (
                f"Bound mismatch for {label}: "
                f"expected ({exp_min}, {exp_max}), "
                f"got ({actual.min}, {actual.max})"
            )

    def test_bc_template_is_hub_clamp(self):
        """bc_template.type is hub_clamp with correct params from BCConfig."""
        cfg = load_machine_yaml(_ADAPTER_YAML)
        assert cfg.bc_template.type == "hub_clamp"
        assert cfg.bc_template.params.get("hub_center") == [0.0, 0.0]
        assert cfg.bc_template.params.get("hub_radius") == 0.15

    def test_axis_is_auto(self):
        """axis is set to 'auto' (discovered from mesh bounding box)."""
        cfg = load_machine_yaml(_ADAPTER_YAML)
        assert cfg.axis == "auto"

    def test_mesh_scale_factor_is_documented(self):
        """mesh_scale_factor is present (value TBD until axis diagnostic run)."""
        cfg = load_machine_yaml(_ADAPTER_YAML)
        assert cfg.mesh_scale_factor == 1.0, (
            "mesh_scale_factor must be updated after axis diagnostic inside "
            "the dtOO container; see the comment in adapters/machines/tistos.yaml"
        )


# ----------------------------------------------------------------------
# Parity tests (require dtOO + fenicsx container).
# ----------------------------------------------------------------------

class TestTistosExportParity:
    """Verify DtooAdapter export matches the golden mesh checksum."""
    pytestmark = pytest.mark.skipif(
        not _DTOO_AVAILABLE,
        reason="dtOOPythonSWIG not available — run inside the dtOO container "
               "(atismer/dtoo-opensuse:stable) with LD_LIBRARY_PATH set",
    )

    def test_mesh_export_produces_msh(self, tmp_path: Path):
        """DtooAdapter.export_mesh({}) writes a .msh file at the temp path."""
        adapter = DtooAdapter(str(_ADAPTER_YAML))
        output_msh = str(tmp_path / "tistos.msh")
        mesh_path = adapter.export_mesh({}, output_msh=output_msh)
        assert Path(mesh_path).exists(), "export_mesh did not produce a mesh file"
        assert Path(mesh_path).stat().st_size > 0, "exported mesh is empty"

    def test_mesh_checksum_matches_golden(self, tmp_path: Path):
        """SHA-256 of the exported mesh matches the frozen golden checksum.

        If the golden checksum is TBD, the test xfail-s so the first container
        run records the actual hash for manual update.
        """
        golden = json.loads(_GOLDEN_PATH.read_text())
        expected_hash = golden["mesh_hash"]

        adapter = DtooAdapter(str(_ADAPTER_YAML))
        output_msh = str(tmp_path / "tistos.msh")
        mesh_path = adapter.export_mesh({}, output_msh=output_msh)
        actual_hash = _sha256_file(mesh_path)

        if expected_hash.startswith("TBD"):
            pytest.xfail(
                f"Golden mesh_hash is TBD. Actual SHA-256: {actual_hash}\n"
                f"Update tests/characterization/golden/tistos_coarse.json with this value."
            )

        assert actual_hash == expected_hash, (
            f"Mesh checksum mismatch!\n"
            f"  expected: {expected_hash}\n"
            f"  actual:   {actual_hash}\n"
            f"If the change is intentional, update golden/tistos_coarse.json"
        )


@pytest.mark.skipif(
    not _DTOO_AVAILABLE,
    reason="dtOOPythonSWIG not available — run inside the dtOO container "
           "(atismer/dtoo-opensuse:stable) with LD_LIBRARY_PATH set",
)
class TestTistosSolverParity:
    """Verify the solver frequencies and mode shapes match the golden reference."""

    @pytest.fixture
    def solver_result(self, tmp_path: Path):
        """Run dtOO export + modal solve; return (frequencies, eigenvectors, domain)."""
        adapter = DtooAdapter(str(_ADAPTER_YAML))
        output_msh = str(tmp_path / "tistos.msh")
        mesh_path = adapter.export_mesh({}, output_msh=output_msh)

        from eigenfrequencies.config import MaterialConfig, SolverConfig
        from eigenfrequencies.io import load_and_prepare_mesh

        bc_cfg = adapter.bc()
        mesh_config = type("MeshConfig", (), {"msh_path": mesh_path})()
        domain = load_and_prepare_mesh(mesh_config)

        material = MaterialConfig()
        solver_cfg = SolverConfig(
            num_eigenvalues=10,
            tolerance=1e-6,
            element_degree=1,
            solver_backend="scipy",
        )

        from eigenfrequencies.solver import ModalSolver
        solver = ModalSolver(domain, material, bc_cfg, solver_cfg)
        eigenvalues, eigenvectors = solver.solve()
        frequencies = solver.compute_frequencies(eigenvalues)
        return frequencies, eigenvectors, domain

    def _mode_shapes(self, eigenvectors, mesh_coords):
        """Return displacement-norm vector per mode for MAC computation."""
        num_nodes = len(mesh_coords)
        norms = []
        for ev in eigenvectors:
            if len(ev) >= num_nodes * 3:
                u = ev[:num_nodes * 3].reshape((num_nodes, 3))
            else:
                u = ev.reshape((-1, 3))
            disp_norm = np.linalg.norm(u, axis=1)
            norms.append(disp_norm)
        return norms

    def test_frequencies_match_golden(self, solver_result):
        """Solver frequencies match golden within 1e-4 relative error.

        If the golden frequencies are TBD, the test xfail-s so the first
        container run records the actual values for manual update.
        """
        frequencies, eigenvectors, domain = solver_result
        golden = json.loads(_GOLDEN_PATH.read_text())
        expected_freqs = golden["frequencies"]

        if isinstance(expected_freqs, str) and expected_freqs.startswith("TBD"):
            pytest.xfail(
                f"Golden frequencies are TBD.\n"
                f"Actual first-10 frequencies: {frequencies.tolist()[:10]}\n"
                f"Update tests/characterization/golden/tistos_coarse.json with these values."
            )

        mode_shapes = self._mode_shapes(eigenvectors, domain.geometry.x)

        assert len(frequencies) == len(expected_freqs), (
            f"Frequency count mismatch: got {len(frequencies)}, "
            f"expected {len(expected_freqs)}"
        )

        for i, (computed, expected) in enumerate(zip(frequencies, expected_freqs)):
            rel_err = (
                abs(computed - expected) / abs(expected)
                if expected != 0 else abs(computed)
            )
            assert rel_err <= _FREQ_REL_TOL, (
                f"tistos mode {i+1} frequency drift: "
                f"computed={computed:.6f} Hz, expected={expected:.6f} Hz, "
                f"rel_err={rel_err:.6e}"
            )

        # Store computed values on the fixture for the MAC test below.
        solver_result["mode_shapes"] = mode_shapes

    def test_mode_shapes_mac_above_0999(self, solver_result):
        """Mode shapes match golden with MAC >= 0.999 for every mode.

        If the golden mode_shapes are TBD, the test xfail-s.
        """
        golden = json.loads(_GOLDEN_PATH.read_text())
        expected_shapes = golden["mode_shapes"]

        if isinstance(expected_shapes, str) and expected_shapes.startswith("TBD"):
            pytest.xfail(
                "Golden mode_shapes are TBD — run the dtOO container first "
                "to record the actual eigenvectors; update "
                "tests/characterization/golden/tistos_coarse.json"
            )

        mode_shapes = solver_result.get("mode_shapes")
        if mode_shapes is None:
            # Dependent on test_frequencies_match_golden running first.
            frequencies, eigenvectors, domain = solver_result
            mode_shapes = self._mode_shapes(eigenvectors, domain.geometry.x)

        assert len(mode_shapes) == len(expected_shapes), (
            f"Mode-shape count mismatch: got {len(mode_shapes)}, "
            f"expected {len(expected_shapes)}"
        )

        for i, (computed, expected) in enumerate(zip(mode_shapes, expected_shapes)):
            mac = _compute_mac(computed, expected)
            assert mac >= _MAC_MIN, (
                f"tistos mode {i+1} MAC too low: mac={mac:.6f} "
                f"(minimum {_MAC_MIN})"
            )
