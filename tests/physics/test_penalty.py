"""Tests for eigenfrequencies.penalty — replay golden objective cases.

These tests verify that the ported penalty and objective functions reproduce
the frozen golden values from the original turbine_runner runs.
"""

import json
import os

import pytest

from eigenfrequencies.config import CFDConfig, ObjectiveConfig, OptimizationConfig
from eigenfrequencies.penalty import (
    band_report,
    cfd_scalar,
    combined_objective,
    compute_penalty,
    resonance_term,
)

_HERE = os.path.dirname(os.path.abspath(__file__))
_GOLDEN_PATH = os.path.join(
    os.path.dirname(_HERE), "characterization", "golden", "objective_cases.json"
)


def _load_golden():
    with open(_GOLDEN_PATH) as fh:
        return json.load(fh)


def _rel_close(a, b, rtol=1e-9):
    if a == b:
        return True
    scale = max(abs(a), abs(b), 1.0)
    return abs(a - b) / scale <= rtol


@pytest.fixture(scope="module")
def golden_cases():
    return _load_golden()


@pytest.fixture(scope="module")
def configs():
    return {
        "opt_cfg": OptimizationConfig(n_rpm=72.0),
        "cfd_cfg": CFDConfig(n_rpm=72.0),
        "obj_cfg": ObjectiveConfig(),
    }


@pytest.mark.parametrize("case_index", list(range(5)))
def test_replay_matches_golden(case_index, golden_cases, configs):
    """Replay each golden case against the package imports."""
    case = golden_cases[case_index]
    inputs = case["inputs"]
    frozen = case["frozen"]

    frequencies = inputs["frequencies"]
    cfd_dict = inputs["cfd"]

    opt_cfg = configs["opt_cfg"]
    cfd_cfg = configs["cfd_cfg"]
    obj_cfg = configs["obj_cfg"]

    assert _rel_close(
        resonance_term(frequencies, opt_cfg, obj_cfg),
        frozen["resonance_term"],
    )
    assert _rel_close(
        cfd_scalar(cfd_dict, cfd_cfg, obj_cfg),
        frozen["cfd_scalar"],
    )
    total, breakdown = combined_objective(cfd_dict, frequencies, cfd_cfg, opt_cfg, obj_cfg)
    assert _rel_close(total, frozen["combined_objective"]["total"])
    assert _rel_close(breakdown["f_cfd"], frozen["combined_objective"]["breakdown"]["f_cfd"])
    assert _rel_close(breakdown["f_resonance"], frozen["combined_objective"]["breakdown"]["f_resonance"])
    assert breakdown["resonance"] == frozen["combined_objective"]["breakdown"]["resonance"]


def test_band_report_no_violation():
    """Frequencies outside all bands produce an OK report."""
    opt_cfg = OptimizationConfig(n_rpm=72.0)
    freqs = [0.0, 10.0, 100.0]  # 10 Hz is below first band [16.6, 26.6]
    report = band_report(freqs, opt_cfg)
    assert report.startswith("OK: no mode in forbidden bands")


def test_band_report_violation():
    """A frequency inside a band produces a VIOLATION report."""
    opt_cfg = OptimizationConfig(n_rpm=72.0)
    freqs = [21.6]  # inside first band [16.6, 26.6]
    report = band_report(freqs, opt_cfg)
    assert report.startswith("VIOLATION: mode 1=21.6Hz")


def test_compute_penalty_zero_outside_band():
    """Frequencies outside all bands yield zero penalty."""
    opt_cfg = OptimizationConfig(n_rpm=72.0)
    assert compute_penalty([0.0, 10.0, 100.0], opt_cfg) == 0.0


def test_compute_penalty_nonzero_inside_band():
    """A frequency at the centre of a band yields the maximum depth penalty."""
    opt_cfg = OptimizationConfig(n_rpm=72.0, penalty_k=1.0)
    f_bp = opt_cfg.Z_guidevanes * opt_cfg.n_rpm / 60.0  # 21.6
    centre = f_bp
    margin = max(opt_cfg.margin_hz, centre * opt_cfg.margin_fraction)  # 5.0
    expected = margin  # depth at centre = margin
    assert compute_penalty([centre], opt_cfg) == pytest.approx(expected, rel=1e-9)
