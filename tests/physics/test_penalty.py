"""Tests for eigenfrequencies.penalty — resonance band logic."""

import pytest

from eigenfrequencies.config import ResonanceConfig
from eigenfrequencies.penalty import band_report, compute_penalty, violating_modes


@pytest.fixture
def cfg():
    return ResonanceConfig(n_rpm=72.0)


def test_band_report_no_violation(cfg):
    """Frequencies outside all bands produce an OK report."""
    report = band_report([0.0, 10.0, 100.0], cfg)
    assert report.startswith("OK: no mode in forbidden bands")


def test_band_report_violation(cfg):
    """A frequency inside a band produces a VIOLATION report."""
    report = band_report([21.6], cfg)
    assert report.startswith("VIOLATION: mode 1=21.6Hz")


def test_compute_penalty_zero_outside_band(cfg):
    """Frequencies outside all bands yield zero penalty."""
    assert compute_penalty([0.0, 10.0, 100.0], cfg) == 0.0


def test_compute_penalty_nonzero_inside_band(cfg):
    """A frequency at the centre of a band yields the maximum depth penalty."""
    f_bp = cfg.Z_guidevanes * cfg.n_rpm / 60.0
    margin = max(cfg.margin_hz, f_bp * cfg.margin_fraction)
    assert compute_penalty([f_bp], cfg) == pytest.approx(margin, rel=1e-9)


def test_violating_modes_empty(cfg):
    assert violating_modes([0.0, 10.0, 100.0], cfg) == []


def test_violating_modes_lists_indices(cfg):
    assert violating_modes([21.6, 43.2], cfg) == [1, 2]


def test_violating_modes_skips_non_violators(cfg):
    assert violating_modes([10.0, 43.2], cfg) == [2]
