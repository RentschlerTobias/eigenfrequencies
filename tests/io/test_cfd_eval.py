"""Tests for the OpenFOAM postProcessing reader.

The column layout mirrors rl_framework/xml/tistos_ru_of.xml:
surfaceFieldValue/cavitationVolume write [time, value]; the forces
functionObject writes [time, total(3), pressure(3), viscous(3)].
"""

import os

import pytest

from eigenfrequencies.config import CFDConfig
from eigenfrequencies.io.cfd_eval import evaluate_cfd


def _write(path: str, text: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as fh:
        fh.write(text)


def _build_case(tmpdir, *, last_time=500, moment_z=-100.0, ramp=0.0):
    """Write a minimal postProcessing tree with 100 iterations per quantity.

    ``ramp`` adds a linear drift so the trailing average differs from the last
    row, which is what distinguishes averaging from single-row reads.
    """
    pp = os.path.join(tmpdir, "postProcessing")
    times = list(range(last_time - 99, last_time + 1))

    def scalar(name, value):
        rows = "\n".join(f"{t}\t{value + ramp * i}" for i, t in enumerate(times))
        _write(os.path.join(pp, name, "100", f"{name}.dat"), f"# Time value\n{rows}\n")

    scalar("Q_ru_in", 2.0)
    scalar("ptot_ru_in", 1000.0)
    scalar("ptot_ru_out", -22554.0)  # gives dH ~ -2.4 m
    scalar("V_CAV", 0.001)

    rows = "\n".join(
        f"{t}\t(0 0 {moment_z + ramp * i})\t(0 0 0)\t(0 0 0)" for i, t in enumerate(times)
    )
    _write(os.path.join(pp, "forces", "100", "moment.dat"), f"# Time total pressure viscous\n{rows}\n")
    return tmpdir


def _cfg(**kw):
    cfg = CFDConfig(n_rpm=72.0)
    for k, v in kw.items():
        setattr(cfg, k, v)
    return cfg


class TestEvaluateCfdHappyPath:
    def test_reads_all_quantities(self, tmp_path):
        case = _build_case(str(tmp_path))
        out = evaluate_cfd(case, _cfg(end_time=500))
        assert out["ok"] is True, out.get("error")
        assert out["Q"] == pytest.approx(2.0)
        assert out["dH"] == pytest.approx((-22554.0 - 1000.0) / 9.81)
        # total_z is index 3 of [time, total(3), pressure(3), viscous(3)]
        assert out["P"] == pytest.approx(-100.0 * _cfg().omega)

    def test_averages_the_trailing_iterations(self, tmp_path):
        """A drifting signal must average, not report the final row."""
        case = _build_case(str(tmp_path), ramp=1.0)
        out = evaluate_cfd(case, _cfg(end_time=500))
        assert out["ok"] is True, out.get("error")
        # 100 rows, trailing 10 % -> rows 90..99, offsets 90..99, mean 94.5
        assert out["Q"] == pytest.approx(2.0 + 94.5)
        assert out["Q"] != pytest.approx(2.0 + 99.0), "read the last row instead of averaging"


class TestEvaluateCfdRejects:
    def test_run_that_stopped_early_is_rejected(self, tmp_path):
        """A truncated solve must not reach the objective as a valid result."""
        case = _build_case(str(tmp_path), last_time=300)
        out = evaluate_cfd(case, _cfg(end_time=500))
        assert out["ok"] is False
        assert "Max number of iterations not reached" in out["error"]

    def test_pump_is_rejected(self, tmp_path):
        case = _build_case(str(tmp_path), moment_z=-1e9)
        out = evaluate_cfd(case, _cfg(end_time=500))
        assert out["ok"] is False
        assert "Pump detected" in out["error"]

    def test_missing_tree_reports_instead_of_raising(self, tmp_path):
        out = evaluate_cfd(str(tmp_path), _cfg(end_time=500))
        assert out["ok"] is False
        assert "FileNotFoundError" in out["error"]
