"""Tests for the ``dtoo`` CLI sub-group: discover-axis and measure-scale."""

from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from eigenfrequencies.cli import EXIT_CONFIG_ERROR, EXIT_OK, EXIT_SOLVE_ERROR, app

runner = CliRunner()


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

AXIS_RESULT = {
    "file": "/fake/runner.msh",
    "topology_dim": 3,
    "num_nodes": 1234,
    "axes": {
        "x": {"min": -0.5, "max": 0.5, "span": 1.0},
        "y": {"min": -0.25, "max": 0.25, "span": 0.5},
        "z": {"min": -1.0, "max": 1.0, "span": 2.0},
    },
}


# ---------------------------------------------------------------------------
# discover-axis
# ---------------------------------------------------------------------------

class TestDiscoverAxisHappyPath:
    def test_discover_axis_z_is_longest(self, tmp_path: Path):
        mesh = tmp_path / "runner.msh"
        mesh.touch()

        with patch(
            "eigenfrequencies.io.axis.inspect_mesh", return_value=AXIS_RESULT
        ):
            result = runner.invoke(app, ["dtoo", "discover-axis", "--mesh", str(mesh)])

        assert result.exit_code == EXIT_OK, result.output
        assert "rotation_axis: z" in result.output
        assert "confidence: 4.0000" in result.output  # span_z / span_y = 2.0 / 0.5
        assert "<-- rotation_axis" in result.output
        assert "z:" in result.output and "span=2.0000" in result.output
        assert "x:" in result.output
        assert "y:" in result.output

    def test_discover_axis_x_is_longest(self, tmp_path: Path):
        mesh = tmp_path / "runner.msh"
        mesh.touch()

        result_x_longest = {
            "axes": {
                "x": {"min": 0.0, "max": 3.0, "span": 3.0},
                "y": {"min": -0.1, "max": 0.1, "span": 0.2},
                "z": {"min": -0.1, "max": 0.1, "span": 0.2},
            }
        }

        with patch(
            "eigenfrequencies.io.axis.inspect_mesh", return_value=result_x_longest
        ):
            result = runner.invoke(
                app, ["dtoo", "discover-axis", "--mesh", str(mesh)]
            )

        assert result.exit_code == EXIT_OK, result.output
        assert "rotation_axis: x" in result.output
        assert "confidence: 15.0000" in result.output  # 3.0 / 0.2


class TestDiscoverAxisFailurePaths:
    def test_discover_axis_missing_mesh_exits_2(self):
        result = runner.invoke(
            app, ["dtoo", "discover-axis", "--mesh", "/nonexistent.msh"]
        )
        assert result.exit_code == EXIT_CONFIG_ERROR
        assert "Mesh file not found" in result.output

    def test_discover_axis_inspect_mesh_error_exits_3(self, tmp_path: Path):
        mesh = tmp_path / "runner.msh"
        mesh.touch()

        with patch(
            "eigenfrequencies.io.axis.inspect_mesh",
            side_effect=RuntimeError("dolfinx not available"),
        ):
            result = runner.invoke(
                app, ["dtoo", "discover-axis", "--mesh", str(mesh)]
            )

        assert result.exit_code == EXIT_SOLVE_ERROR
        assert "dolfinx not available" in result.output


# ---------------------------------------------------------------------------
# measure-scale
# ---------------------------------------------------------------------------

class TestMeasureScaleHappyPath:
    def test_measure_scale_prints_yaml_snippet(self, tmp_path: Path):
        mesh = tmp_path / "runner.msh"
        mesh.touch()

        with patch(
            "eigenfrequencies.io.axis.inspect_mesh", return_value=AXIS_RESULT
        ):
            result = runner.invoke(
                app,
                [
                    "dtoo",
                    "measure-scale",
                    "--mesh",
                    str(mesh),
                    "--physical-length",
                    "0.5",
                    "--feature-desc",
                    "hub bore diameter",
                ],
            )

        assert result.exit_code == EXIT_OK, result.output
        assert "# YAML snippet for machine file" in result.output
        assert "mesh_scale_factor: 0.25000000" in result.output
        assert "# Feature measured: hub bore diameter" in result.output
        assert "# Longest axis: z  (mesh span: 2.000000 m)" in result.output
        assert "# Physical length: 0.500000 m" in result.output

    def test_measure_scale_scale_factor_correct(self, tmp_path: Path):
        mesh = tmp_path / "runner.msh"
        mesh.touch()

        result_x_longest = {
            "axes": {
                "x": {"min": 0.0, "max": 0.25, "span": 0.25},
                "y": {"min": -1.0, "max": 1.0, "span": 0.2},
                "z": {"min": -1.0, "max": 1.0, "span": 0.1},
            }
        }

        with patch(
            "eigenfrequencies.io.axis.inspect_mesh", return_value=result_x_longest
        ):
            result = runner.invoke(
                app,
                [
                    "dtoo",
                    "measure-scale",
                    "--mesh",
                    str(mesh),
                    "--physical-length",
                    "1.0",
                    "--feature-desc",
                    "rotor radius",
                ],
            )

        assert result.exit_code == EXIT_OK, result.output
        assert "Longest axis: x" in result.output
        assert "mesh_scale_factor: 4.00000000" in result.output  # 1.0 / 0.25


class TestMeasureScaleFailurePaths:
    def test_measure_scale_missing_mesh_exits_2(self):
        result = runner.invoke(
            app,
            [
                "dtoo",
                "measure-scale",
                "--mesh",
                "/nonexistent.msh",
                "--physical-length",
                "1.0",
                "--feature-desc",
                "test",
            ],
        )
        assert result.exit_code == EXIT_CONFIG_ERROR
        assert "Mesh file not found" in result.output

    def test_measure_scale_negative_physical_length_exits_2(self, tmp_path: Path):
        mesh = tmp_path / "runner.msh"
        mesh.touch()

        result = runner.invoke(
            app,
            [
                "dtoo",
                "measure-scale",
                "--mesh",
                str(mesh),
                "--physical-length",
                "-0.5",
                "--feature-desc",
                "test",
            ],
        )
        assert result.exit_code == EXIT_CONFIG_ERROR
        assert "must be positive" in result.output

    def test_measure_scale_zero_physical_length_exits_2(self, tmp_path: Path):
        mesh = tmp_path / "runner.msh"
        mesh.touch()

        result = runner.invoke(
            app,
            [
                "dtoo",
                "measure-scale",
                "--mesh",
                str(mesh),
                "--physical-length",
                "0",
                "--feature-desc",
                "test",
            ],
        )
        assert result.exit_code == EXIT_CONFIG_ERROR
        assert "must be positive" in result.output

    def test_measure_scale_inspect_mesh_error_exits_3(self, tmp_path: Path):
        mesh = tmp_path / "runner.msh"
        mesh.touch()

        with patch(
            "eigenfrequencies.io.axis.inspect_mesh",
            side_effect=RuntimeError("mesh corrupted"),
        ):
            result = runner.invoke(
                app,
                [
                    "dtoo",
                    "measure-scale",
                    "--mesh",
                    str(mesh),
                    "--physical-length",
                    "1.0",
                    "--feature-desc",
                    "test",
                ],
            )

        assert result.exit_code == EXIT_SOLVE_ERROR
        assert "mesh corrupted" in result.output

    def test_measure_scale_zero_mesh_span_exits_3(self, tmp_path: Path):
        mesh = tmp_path / "runner.msh"
        mesh.touch()

        zero_span_result = {
            "axes": {
                "x": {"min": 0.0, "max": 0.0, "span": 0.0},
                "y": {"min": -1.0, "max": 1.0, "span": 0.0},
                "z": {"min": -1.0, "max": 1.0, "span": 0.0},
            }
        }

        with patch(
            "eigenfrequencies.io.axis.inspect_mesh", return_value=zero_span_result
        ):
            result = runner.invoke(
                app,
                [
                    "dtoo",
                    "measure-scale",
                    "--mesh",
                    str(mesh),
                    "--physical-length",
                    "1.0",
                    "--feature-desc",
                    "test",
                ],
            )

        assert result.exit_code == EXIT_SOLVE_ERROR
        assert "zero or negative" in result.output or "span is zero" in result.output
