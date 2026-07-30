"""Tests for the ``report`` CLI command."""

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from eigenfrequencies.cli import EXIT_CONFIG_ERROR, EXIT_OK, app

runner = CliRunner()


@pytest.fixture
def run_dir_with_result(tmp_path: Path) -> Path:
    """Create a temporary run directory with an optimization_result.json."""
    run_dir = tmp_path / "run_001"
    run_dir.mkdir()
    result = {
        "best_design": [0.1, -0.2],
        "best_objective": 0.05,
        "evaluations": 50,
        "budget": 50,
        "optimizer": "de",
        "history": [
            {
                "generation": 0,
                "designs": [[1.0, 2.0], [3.0, 4.0]],
                "objectives": [5.0, 25.0],
            },
        ],
    }
    with open(run_dir / "optimization_result.json", "w") as fh:
        json.dump(result, fh)
    return run_dir


class TestReportHappyPath:
    def test_report_renders_summary(self, run_dir_with_result: Path):
        """Happy path: report prints best design and objective."""
        result = runner.invoke(app, ["report", "--run-dir", str(run_dir_with_result)])
        assert result.exit_code == EXIT_OK, result.output
        assert "Optimization Report" in result.output
        assert "Best design vector: [0.1, -0.2]" in result.output
        assert "Best objective value: 0.050000" in result.output
        assert "Evaluations: 50 / 50" in result.output
        assert "Objective Breakdown" in result.output
        assert "Frequency Table vs Forbidden Band" in result.output

    def test_report_with_validation_reference(self, run_dir_with_result: Path):
        """Report includes comparison table when validation_reference.json exists."""
        ref = {
            "best_design": [0.0, 0.0],
            "best_objective": 0.0,
        }
        with open(run_dir_with_result / "validation_reference.json", "w") as fh:
            json.dump(ref, fh)

        result = runner.invoke(app, ["report", "--run-dir", str(run_dir_with_result)])
        assert result.exit_code == EXIT_OK, result.output
        assert "Validation Reference Comparison" in result.output
        assert "reference design" in result.output
        assert "reference obj" in result.output


class TestReportFailurePaths:
    def test_report_missing_run_dir_exits_2(self):
        """Missing --run-dir yields exit code 2."""
        result = runner.invoke(app, ["report", "--run-dir", "/nonexistent/run"])
        assert result.exit_code == EXIT_CONFIG_ERROR
        assert "Run directory not found" in result.output

    def test_report_missing_result_file_exits_2(self, tmp_path: Path):
        """Run directory without optimization_result.json yields exit code 2."""
        empty_dir = tmp_path / "empty_run"
        empty_dir.mkdir()
        result = runner.invoke(app, ["report", "--run-dir", str(empty_dir)])
        assert result.exit_code == EXIT_CONFIG_ERROR
        assert "Result file not found" in result.output

    def test_report_invalid_json_exits_2(self, tmp_path: Path):
        """Invalid optimization_result.json yields exit code 2."""
        bad_dir = tmp_path / "bad_run"
        bad_dir.mkdir()
        (bad_dir / "optimization_result.json").write_text("not json")
        result = runner.invoke(app, ["report", "--run-dir", str(bad_dir)])
        assert result.exit_code == EXIT_CONFIG_ERROR
        assert "Failed to read result file" in result.output
