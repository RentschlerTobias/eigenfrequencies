"""Tests for the ``optimize`` CLI command."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from eigenfrequencies.cli import EXIT_CONFIG_ERROR, EXIT_OK, app

runner = CliRunner()


@pytest.fixture
def minimal_optimize_config_yaml(tmp_path: Path) -> Path:
    """Write a minimal valid YAML config with design bounds to a temp file."""
    cfg = tmp_path / "optimize.yaml"
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
  params:
    x1: [-5.0, 5.0, 0.0]
    x2: [-5.0, 5.0, 0.0]
de:
  pop_size: 10
  mutation: 0.8
  crossover: 0.9
  max_generations: 5
  tol: 0.01
  seed: 42
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


class TestOptimizeHappyPath:
    def test_optimize_runs_and_produces_result_json(self, minimal_optimize_config_yaml: Path, tmp_path: Path):
        """Happy path: optimizer runs and writes optimization_result.json."""
        out_dir = tmp_path / "output"
        result = runner.invoke(
            app,
            [
                "optimize",
                "--config", str(minimal_optimize_config_yaml),
                "--optimizer", "de",
                "--budget", "20",
                "--out", str(out_dir),
            ],
        )
        assert result.exit_code == EXIT_OK, result.output
        assert "Optimization complete" in result.output
        result_path = out_dir / "optimization_result.json"
        assert result_path.is_file()
        with open(result_path) as fh:
            data = json.load(fh)
        assert "best_design" in data
        assert "best_objective" in data
        assert "history" in data
        assert data["evaluations"] == 20
        assert data["budget"] == 20
        assert data["optimizer"] == "de"

    def test_optimize_with_budget_default(self, minimal_optimize_config_yaml: Path, tmp_path: Path):
        """Default budget equals pop_size * max_generations."""
        out_dir = tmp_path / "output"
        result = runner.invoke(
            app,
            [
                "optimize",
                "--config", str(minimal_optimize_config_yaml),
                "--optimizer", "de",
                "--out", str(out_dir),
            ],
        )
        assert result.exit_code == EXIT_OK, result.output
        result_path = out_dir / "optimization_result.json"
        assert result_path.is_file()
        with open(result_path) as fh:
            data = json.load(fh)
        assert data["budget"] == 50  # pop_size=10 * max_generations=5
        assert data["evaluations"] == 50

    def test_optimize_resume(self, minimal_optimize_config_yaml: Path, tmp_path: Path):
        """Resume from a prior state dict continues optimization."""
        from eigenfrequencies.optimize import DEOptimizer

        out_dir = tmp_path / "output"
        opt = DEOptimizer({
            "bounds": [(-5.0, 5.0), (-5.0, 5.0)],
            "pop_size": 10,
            "seed": 42,
        })
        designs = opt.ask(10)
        objectives = [sum(v * v for v in d.vector) for d in designs]
        opt.tell(designs, objectives)
        state = opt.state_dict()

        state_path = tmp_path / "state.json"
        with open(state_path, "w") as fh:
            json.dump(state, fh)

        # Resume run
        result = runner.invoke(
            app,
            [
                "optimize",
                "--config", str(minimal_optimize_config_yaml),
                "--optimizer", "de",
                "--budget", "10",
                "--resume", str(state_path),
                "--out", str(out_dir),
            ],
        )
        assert result.exit_code == EXIT_OK, result.output
        assert "Optimization complete" in result.output
        result_path = out_dir / "optimization_result.json"
        assert result_path.is_file()


class TestOptimizeFailurePaths:
    def test_optimize_missing_config_exits_2(self):
        """Missing config file yields exit code 2."""
        result = runner.invoke(app, ["optimize", "--config", "/nonexistent.yaml", "--optimizer", "de"])
        assert result.exit_code == EXIT_CONFIG_ERROR
        assert "Failed to load config" in result.output or "Config error" in result.output

    def test_optimize_unknown_optimizer_exits_2(self, minimal_optimize_config_yaml: Path):
        """Unknown --optimizer value yields exit code 2."""
        result = runner.invoke(
            app,
            [
                "optimize",
                "--config", str(minimal_optimize_config_yaml),
                "--optimizer", "xyz",
            ],
        )
        assert result.exit_code == EXIT_CONFIG_ERROR
        assert "Unknown optimizer" in result.output

    def test_optimize_unimplemented_backends_exits_2(self, minimal_optimize_config_yaml: Path):
        """Unregistered backends (pso, rl) yield exit code 2."""
        for backend in ("pso", "rl"):
            result = runner.invoke(
                app,
                [
                    "optimize",
                    "--config", str(minimal_optimize_config_yaml),
                    "--optimizer", backend,
                ],
            )
            assert result.exit_code == EXIT_CONFIG_ERROR, f"{backend} should exit 2, got {result.exit_code}: {result.output}"
            assert "Unknown optimizer" in result.output

    def test_optimize_islands_exits_2(self, minimal_optimize_config_yaml: Path):
        """--islands > 1 yields exit code 2 with 'not implemented yet'."""
        result = runner.invoke(
            app,
            [
                "optimize",
                "--config", str(minimal_optimize_config_yaml),
                "--optimizer", "de",
                "--islands", "2",
            ],
        )
        assert result.exit_code == EXIT_CONFIG_ERROR
        assert "not implemented yet" in result.output.lower()

    def test_optimize_empty_design_params_exits_2(self, tmp_path: Path):
        """Config with empty design.params yields exit code 2."""
        cfg = tmp_path / "empty_design.yaml"
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
  mode: axial_plane
  plane_value: 0.0
  plane_tol: 1.0e-6
mesh:
  msh_path: data/runner.msh
  gdim: 3
solver:
  num_eigenvalues: 10
  tolerance: 1.0e-6
  solver_backend: scipy
design:
  params: {}
de:
  pop_size: 10
  mutation: 0.8
  crossover: 0.9
  max_generations: 5
  tol: 0.01
  seed: 42
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
output:
  output_dir: output
  save_xdmf: true
  results_json: frequencies.json
"""
        )
        result = runner.invoke(
            app,
            [
                "optimize",
                "--config", str(cfg),
                "--optimizer", "de",
            ],
        )
        assert result.exit_code == EXIT_CONFIG_ERROR
        assert "no design parameters" in result.output.lower()

    def test_optimize_resume_missing_file_exits_2(self, minimal_optimize_config_yaml: Path):
        """--resume pointing to nonexistent file yields exit code 2."""
        result = runner.invoke(
            app,
            [
                "optimize",
                "--config", str(minimal_optimize_config_yaml),
                "--optimizer", "de",
                "--resume", "/nonexistent/state.json",
            ],
        )
        assert result.exit_code == EXIT_CONFIG_ERROR
        assert "Resume file not found" in result.output
