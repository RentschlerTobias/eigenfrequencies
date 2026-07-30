"""Tests for the ``validate`` CLI command."""

from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from eigenfrequencies.cli import (
    EXIT_CONFIG_ERROR,
    EXIT_OK,
    EXIT_SOLVE_ERROR,
    EXIT_VALIDATION_DEVIATION,
    app,
)

runner = CliRunner()


class TestValidateBeam:
    def test_beam_validation_passes(self):
        """Happy path: beam validation within tolerance exits 0."""
        with patch("eigenfrequencies.cli._run_beam_validation", return_value=(
            True,
            {
                "deviations": [
                    {"mode": 1, "fem_hz": 8.39, "analytical_hz": 8.36, "error_pct": 0.36},
                ],
            },
        )):
            result = runner.invoke(app, ["validate", "--suite", "beam"])

        assert result.exit_code == EXIT_OK, result.output
        assert "PASSED" in result.output

    def test_beam_validation_fails(self):
        """Beam deviation > 5% yields exit code 4."""
        with patch("eigenfrequencies.cli._run_beam_validation", return_value=(
            False,
            {
                "deviations": [
                    {"mode": 1, "fem_hz": 8.80, "analytical_hz": 8.36, "error_pct": 5.26},
                ],
            },
        )):
            result = runner.invoke(app, ["validate", "--suite", "beam"])

        assert result.exit_code == EXIT_VALIDATION_DEVIATION
        assert "FAILED" in result.output
        assert "5.26%" in result.output

    def test_beam_validation_error_exits_3(self):
        """Unexpected exception during beam validation yields exit code 3."""
        with patch(
            "eigenfrequencies.cli._run_beam_validation",
            side_effect=RuntimeError("gmsh failed"),
        ):
            result = runner.invoke(app, ["validate", "--suite", "beam"])

        assert result.exit_code == EXIT_SOLVE_ERROR
        assert "gmsh failed" in result.output


class TestValidateTestcase:
    def test_testcase_skip_dolfinx_unavailable(self):
        """dolfinx unavailable prints skip message and exits 0."""
        with patch(
            "eigenfrequencies.cli._run_testcase_validation",
            return_value=(None, {"skip": "dolfinx not available"}),
        ):
            result = runner.invoke(app, ["validate", "--suite", "testcase"])

        assert result.exit_code == EXIT_OK
        assert "dolfinx not available" in result.output

    def test_testcase_skip_env_not_set(self):
        """RUN_TESTCASE_VALIDATION not set prints skip message and exits 0."""
        with patch(
            "eigenfrequencies.cli._run_testcase_validation",
            return_value=(None, {"skip": "Set RUN_TESTCASE_VALIDATION=1"}),
        ):
            result = runner.invoke(app, ["validate", "--suite", "testcase"])

        assert result.exit_code == EXIT_OK
        assert "RUN_TESTCASE_VALIDATION" in result.output

    def test_testcase_passes(self):
        """Testcase validation within tolerance exits 0."""
        with patch(
            "eigenfrequencies.cli._run_testcase_validation",
            return_value=(
                True,
                {
                    "deviations": [
                        {"label": "1ND", "computed_hz": 192.5, "experiment_hz": 192.8, "error_pct": 0.16},
                    ],
                },
            ),
        ):
            result = runner.invoke(app, ["validate", "--suite", "testcase", "--full"])

        assert result.exit_code == EXIT_OK
        assert "PASSED" in result.output

    def test_testcase_fails(self):
        """Testcase deviation > 5% yields exit code 4."""
        with patch(
            "eigenfrequencies.cli._run_testcase_validation",
            return_value=(
                False,
                {
                    "deviations": [
                        {"label": "1ND", "computed_hz": 210.0, "experiment_hz": 192.8, "error_pct": 8.92},
                    ],
                },
            ),
        ):
            result = runner.invoke(app, ["validate", "--suite", "testcase", "--full"])

        assert result.exit_code == EXIT_VALIDATION_DEVIATION
        assert "FAILED" in result.output
        assert "8.92%" in result.output

    def test_testcase_error_exits_3(self):
        """Unexpected exception during testcase validation yields exit code 3."""
        with patch(
            "eigenfrequencies.cli._run_testcase_validation",
            side_effect=RuntimeError("mesh missing"),
        ):
            result = runner.invoke(app, ["validate", "--suite", "testcase"])

        assert result.exit_code == EXIT_SOLVE_ERROR
        assert "mesh missing" in result.output


class TestValidateUnknownSuite:
    def test_unknown_suite_exits_2(self):
        """Unknown --suite value yields exit code 2."""
        result = runner.invoke(app, ["validate", "--suite", "foo"])
        assert result.exit_code == EXIT_CONFIG_ERROR
        assert "Unknown suite" in result.output
