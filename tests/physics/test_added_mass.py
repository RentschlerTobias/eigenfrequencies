"""Tests for eigenfrequencies.added_mass — verify interface and placeholder."""

import numpy as np
import pytest

from eigenfrequencies.added_mass import (
    compare,
    placeholder_ratios,
    rayleigh_ratios,
    wet_from_ratios,
)
from eigenfrequencies.config import WetModeConfig


def test_wet_from_ratios_basic():
    """wet_from_ratios lowers frequencies according to the ratio."""
    dry = np.array([100.0, 200.0])
    ratios = np.array([0.0, 3.0])
    wet = wet_from_ratios(dry, ratios)
    assert wet[0] == pytest.approx(100.0)          # ratio 0 -> no shift
    assert wet[1] == pytest.approx(100.0)          # ratio 3 -> 200 / sqrt(4) = 100


def test_wet_from_ratios_shape_mismatch():
    """Mismatched shapes raise ValueError."""
    with pytest.raises(ValueError, match="ratio shape"):
        wet_from_ratios([100.0], [0.0, 1.0])


def test_wet_from_ratios_negative_ratio():
    """Negative ratios raise ValueError."""
    with pytest.raises(ValueError, match="must be >= 0"):
        wet_from_ratios([100.0], [-0.1])


def test_placeholder_ratios():
    """placeholder_ratios returns a constant array based on fluid density."""
    dry = np.array([100.0, 200.0, 300.0])
    cfg = WetModeConfig(rho_fluid=1000.0)
    ratios = placeholder_ratios(dry, cfg)
    assert ratios.shape == dry.shape
    expected = 0.3 * (1000.0 / 7850.0) * 10.0
    assert np.allclose(ratios, expected)


def test_rayleigh_ratios_raises():
    """rayleigh_ratios must raise NotImplementedError (wet path is deferred)."""
    cfg = WetModeConfig()
    with pytest.raises(NotImplementedError):
        rayleigh_ratios([100.0], None, None, cfg)


def test_compare_uses_placeholder_when_rayleigh_not_implemented():
    """compare falls back to placeholder ratios and reports the method."""
    dry = np.array([100.0, 200.0])
    cfg = WetModeConfig(rho_fluid=1000.0)
    result = compare(dry, cfg)
    assert result["method"] == "placeholder"
    assert len(result["dry_hz"]) == 2
    assert len(result["wet_hz"]) == 2
    assert all(w < d for d, w in zip(result["dry_hz"], result["wet_hz"]))
    assert all(s < 0 for s in result["shift_pct"])
