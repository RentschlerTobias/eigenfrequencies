"""Tests for the ``solve`` CLI command."""

import json
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from eigenfrequencies.cli import EXIT_CONFIG_ERROR, EXIT_OK, EXIT_SOLVE_ERROR, app

runner = CliRunner()


@pytest.fixture
def minimal_config_yaml(tmp_path: Path) -> Path:
    """Write a minimal valid YAML config to a temp file."""
    cfg = tmp_path / "minimal.yaml"
    cfg.write_text(
        """
optimization:
  n_rpm: 72.0
  Z_guidevanes: 18
  max_harmonic: 6
  margin_hz: 5.0
  margin_fraction: 0.05
  penalty_k: 1.0
  max_iter: 40
  method: Nelder-Mead
cfd:
  n_rpm: 72.0
  omega: 7.5398223686155035
  rho: 1000.0
  g: 9.81
  design_head: -2.4
  operating_point: n
  end_time: 500
  post_folder: "100"
material:
  youngs_modulus: 210000000000.0
  density: 7850.0
  poisson_ratio: 0.0
bc:
  axis: x
  hub_center: [0.0, 0.0]
  hub_radius: 0.15
  axial_min: null
  axial_max: null
  mode: axial_plane
  plane_value: 0.0
  plane_tol: 1.0e-6
mesh:
  msh_path: data/runner.msh
  step_path: null
  force_volume_remesh: false
  fallback_element_size: 0.05
  gdim: 3
solver:
  num_eigenvalues: 10
  tolerance: 1.0e-6
  freq_min: 0.0
  freq_max: 1000.0
  element_degree: 2
  solver_backend: scipy
design:
  params: {}
de:
  pop_size: 20
  mutation: 0.8
  crossover: 0.9
  max_generations: 30
  tol: 0.01
  seed: null
objective:
  eval_mode: combined
  w_eta: 1.0
  w_cav: 1.0
  w_head: 1.0
  w_resonance: 1.0
  mode: penalty
  hard_penalty: 1000000.0
wet_mode:
  enabled: false
  compare_dry_wet: true
  rho_fluid: 1000.0
  method: rayleigh
output:
  output_dir: output
  save_xdmf: true
  results_json: frequencies.json
"""
    )
    return cfg


class TestSolveHappyPath:
    def test_solve_runs_and_prints_frequencies(self, minimal_config_yaml: Path, tmp_path: Path):
        """Happy path: solver runs, frequencies printed, JSON written."""
        mock_domain = MagicMock()
        mock_solver = MagicMock()
        mock_solver.solve.return_value = ([1.0, 2.0, 3.0], [MagicMock(), MagicMock(), MagicMock()])
        mock_solver.compute_frequencies.return_value = [8.39, 52.61, 147.38]

        with patch("eigenfrequencies.cli.load_and_prepare_mesh", return_value=mock_domain) as mock_load_mesh, \
             patch("eigenfrequencies.cli.ModalSolver", return_value=mock_solver) as mock_solver_cls, \
             patch("eigenfrequencies.cli.write_results_json") as mock_write_json, \
             patch("eigenfrequencies.cli.write_results_xdmf_vtk") as mock_write_xdmf:
            result = runner.invoke(app, ["solve", "--config", str(minimal_config_yaml)])

        assert result.exit_code == EXIT_OK, result.output
        mock_load_mesh.assert_called_once()
        mock_solver_cls.assert_called_once()
        mock_solver.solve.assert_called_once()
        mock_write_json.assert_called_once()
        mock_write_xdmf.assert_called_once()
        assert "Frequencies (Hz):" in result.output
        assert "Mode 1: 8.3900 Hz" in result.output

    def test_solve_json_flag(self, minimal_config_yaml: Path, tmp_path: Path):
        """--json emits compact JSON to stdout."""
        mock_domain = MagicMock()
        mock_solver = MagicMock()
        mock_solver.solve.return_value = ([1.0, 2.0], [MagicMock(), MagicMock()])
        mock_solver.compute_frequencies.return_value = [8.39, 52.61]

        with patch("eigenfrequencies.cli.load_and_prepare_mesh", return_value=mock_domain), \
             patch("eigenfrequencies.cli.ModalSolver", return_value=mock_solver), \
             patch("eigenfrequencies.cli.write_results_json"), \
             patch("eigenfrequencies.cli.write_results_xdmf_vtk"):
            result = runner.invoke(app, ["solve", "--config", str(minimal_config_yaml), "--json"])

        assert result.exit_code == EXIT_OK, result.output
        parsed = json.loads(result.output.strip().splitlines()[-1])
        assert parsed == {"frequencies_hz": [8.39, 52.61]}

    def test_solve_mesh_override(self, minimal_config_yaml: Path):
        """--mesh overrides the mesh path from config."""
        mock_domain = MagicMock()
        mock_solver = MagicMock()
        mock_solver.solve.return_value = ([1.0], [MagicMock()])
        mock_solver.compute_frequencies.return_value = [1.0]

        with patch("eigenfrequencies.cli.load_and_prepare_mesh", return_value=mock_domain) as mock_load_mesh, \
             patch("eigenfrequencies.cli.ModalSolver", return_value=mock_solver), \
             patch("eigenfrequencies.cli.write_results_json"), \
             patch("eigenfrequencies.cli.write_results_xdmf_vtk"):
            result = runner.invoke(
                app, ["solve", "--config", str(minimal_config_yaml), "--mesh", "/custom/mesh.msh"]
            )

        assert result.exit_code == EXIT_OK, result.output
        args, _ = mock_load_mesh.call_args
        assert args[0].msh_path == "/custom/mesh.msh"

    def test_solve_out_override(self, minimal_config_yaml: Path, tmp_path: Path):
        """--out overrides the output directory from config."""
        mock_domain = MagicMock()
        mock_solver = MagicMock()
        mock_solver.solve.return_value = ([1.0], [MagicMock()])
        mock_solver.compute_frequencies.return_value = [1.0]
        out_dir = tmp_path / "custom_out"

        with patch("eigenfrequencies.cli.load_and_prepare_mesh", return_value=mock_domain), \
             patch("eigenfrequencies.cli.ModalSolver", return_value=mock_solver), \
             patch("eigenfrequencies.cli.write_results_json") as mock_write_json, \
             patch("eigenfrequencies.cli.write_results_xdmf_vtk") as mock_write_xdmf:
            result = runner.invoke(
                app, ["solve", "--config", str(minimal_config_yaml), "--out", str(out_dir)]
            )

        assert result.exit_code == EXIT_OK, result.output
        args = mock_write_json.call_args[0]
        json_path = args[2] if len(args) > 2 else args[0]
        assert str(out_dir) in json_path


class TestSolveFailurePaths:
    def test_solve_nonexistent_config_exits_2(self):
        """Missing config file yields exit code 2."""
        result = runner.invoke(app, ["solve", "--config", "/nonexistent.yaml"])
        assert result.exit_code == EXIT_CONFIG_ERROR
        assert "Failed to load config" in result.output or "Config error" in result.output

    def test_solve_bad_yaml_exits_2(self, tmp_path: Path):
        """Malformed YAML yields exit code 2."""
        bad = tmp_path / "bad.yaml"
        bad.write_text("not: a: valid: yaml: [")
        result = runner.invoke(app, ["solve", "--config", str(bad)])
        assert result.exit_code == EXIT_CONFIG_ERROR

    def test_solve_config_error_exits_2(self, tmp_path: Path):
        """ConfigError (unknown key) yields exit code 2."""
        bad = tmp_path / "bad.yaml"
        bad.write_text(
            "optimization:\n  n_rpm: 72.0\n  Z_guidevanes: 18\n"
            "cfd:\n  n_rpm: 72.0\n  omega: 7.5\nmaterail:\n  youngs_modulus: 1.0\n"
        )
        result = runner.invoke(app, ["solve", "--config", str(bad)])
        assert result.exit_code == EXIT_CONFIG_ERROR
        assert "Unknown key" in result.output or "Config error" in result.output

    def test_solve_solver_config_error_exits_3(self, minimal_config_yaml: Path):
        """SolverConfigError during solve yields exit code 3."""
        mock_domain = MagicMock()
        mock_solver = MagicMock()
        # Use a custom exception class named like SolverConfigError so the
        # isinstance check in the CLI recognises it when we patch the import.
        class FakeSolverConfigError(Exception):
            pass

        mock_solver.solve.side_effect = FakeSolverConfigError("bad backend")

        with patch("eigenfrequencies.cli.load_and_prepare_mesh", return_value=mock_domain), \
             patch("eigenfrequencies.cli.ModalSolver", return_value=mock_solver), \
             patch("eigenfrequencies.cli.SolverConfigError", FakeSolverConfigError):
            result = runner.invoke(app, ["solve", "--config", str(minimal_config_yaml)])

        assert result.exit_code == EXIT_SOLVE_ERROR
        assert "bad backend" in result.output

    def test_solve_generic_solve_error_exits_3(self, minimal_config_yaml: Path):
        """Generic exception during solve yields exit code 3."""
        mock_domain = MagicMock()
        mock_solver = MagicMock()
        mock_solver.solve.side_effect = RuntimeError("solver crashed")

        with patch("eigenfrequencies.cli.load_and_prepare_mesh", return_value=mock_domain), \
             patch("eigenfrequencies.cli.ModalSolver", return_value=mock_solver):
            result = runner.invoke(app, ["solve", "--config", str(minimal_config_yaml)])

        assert result.exit_code == EXIT_SOLVE_ERROR
        assert "solver crashed" in result.output

    def test_solve_mesh_error_exits_3(self, minimal_config_yaml: Path):
        """Mesh loading failure yields exit code 3."""
        with patch(
            "eigenfrequencies.cli.load_and_prepare_mesh",
            side_effect=RuntimeError("mesh missing"),
        ):
            result = runner.invoke(app, ["solve", "--config", str(minimal_config_yaml)])

        assert result.exit_code == EXIT_SOLVE_ERROR
        assert "mesh missing" in result.output


class TestJobResultPublishing:
    """The CLI has to leave its payload where JobStore expects to find it.

    ``JobStore`` starts the CLI with ``JOB_DIR`` set and ``fetch()`` reads
    ``$JOB_DIR/result.json``. The CLI only ever wrote to the configured output
    directory, so every real job finished "done" with nothing to fetch, and the
    MCP ``fetch_results`` tool answered "done but result.json is missing" for a
    solve that had in fact succeeded.
    """

    def test_the_payload_lands_in_the_job_directory(self, tmp_path, monkeypatch):
        from eigenfrequencies.cli import _job_result_path
        from eigenfrequencies.io.results import write_results_json

        job_dir = tmp_path / "job"
        monkeypatch.setenv("JOB_DIR", str(job_dir))
        path = _job_result_path()
        assert path == str(job_dir / "result.json")

        # The same writer the configured output goes through, so the two copies
        # share one schema definition.
        write_results_json([8.39, 52.61], None, path)
        assert json.loads(Path(path).read_text())["frequencies_hz"] == [8.39, 52.61]

    def test_it_is_a_no_op_outside_a_job(self, tmp_path, monkeypatch):
        from eigenfrequencies.cli import _job_result_path

        monkeypatch.delenv("JOB_DIR", raising=False)
        monkeypatch.chdir(tmp_path)

        assert _job_result_path() is None
        assert list(tmp_path.iterdir()) == [], "plain CLI use must write nothing extra"
