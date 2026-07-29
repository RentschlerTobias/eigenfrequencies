"""Tests for eigenfrequencies.bc — verify BC builders produce correct configs."""

import numpy as np
import pytest

from eigenfrequencies.bc import (
    build_predicate,
    clamp,
    foil_clamp,
    free_free,
    hub_clamp,
)
from eigenfrequencies.config import BCConfig


def test_free_free():
    """free_free() returns a BCConfig with mode='free'."""
    cfg = free_free()
    assert cfg.mode == "free"
    assert build_predicate(cfg) is None


def test_clamp_defaults():
    """clamp() returns a radius_band config with sensible defaults."""
    cfg = clamp()
    assert cfg.mode == "radius_band"
    assert cfg.axis == "z"
    assert cfg.hub_center == (0.0, 0.0)
    assert cfg.hub_radius == 0.15
    assert cfg.axial_min is None
    assert cfg.axial_max is None


def test_foil_clamp():
    """foil_clamp() returns an axial_plane config."""
    cfg = foil_clamp(axis="z", plane_value=0.0, plane_tol=1e-6)
    assert cfg.mode == "axial_plane"
    assert cfg.axis == "z"
    assert cfg.plane_value == 0.0
    assert cfg.plane_tol == 1e-6


def test_hub_clamp_alias():
    """hub_clamp() is equivalent to clamp() with the same arguments."""
    cfg_hub = hub_clamp(axis="x", hub_center=(1.0, 2.0), hub_radius=0.2, axial_min=0.0, axial_max=1.0)
    cfg_clamp = clamp(axis="x", hub_center=(1.0, 2.0), hub_radius=0.2, axial_min=0.0, axial_max=1.0)
    assert cfg_hub == cfg_clamp


def test_build_predicate_axial_plane():
    """Predicate for axial_plane matches points on the plane."""
    cfg = foil_clamp(axis="z", plane_value=0.5, plane_tol=1e-3)
    pred = build_predicate(cfg)
    x = np.array([[0.0, 1.0, 2.0], [0.0, 1.0, 2.0], [0.5, 0.5001, 0.6]])
    mask = pred(x)
    assert mask[0] == True
    assert mask[1] == True
    assert mask[2] == False


def test_build_predicate_radius_band():
    """Predicate for radius_band selects points within the hub radius."""
    cfg = clamp(axis="z", hub_center=(0.0, 0.0), hub_radius=1.0)
    pred = build_predicate(cfg)
    x = np.array([[0.0, 2.0, 0.5], [0.0, 0.0, 0.5], [0.0, 0.0, 0.0]])
    mask = pred(x)
    assert mask[0] == True   # radius 0.0 <= 1.0
    assert mask[1] == False  # radius 2.0 > 1.0
    assert mask[2] == True   # radius sqrt(0.5^2+0.5^2) ~0.707 <= 1.0


def test_build_predicate_radius_band_with_axial_limits():
    """Axial min/max further restrict the radius_band predicate."""
    cfg = clamp(axis="z", hub_center=(0.0, 0.0), hub_radius=1.0, axial_min=0.0, axial_max=0.5)
    pred = build_predicate(cfg)
    x = np.array([[0.0, 0.0, 0.0], [0.0, 0.0, 0.0], [-0.1, 0.3, 0.6]])
    mask = pred(x)
    assert mask[0] == False  # z=-0.1 < axial_min
    assert mask[1] == True   # z=0.3 inside axial band
    assert mask[2] == False  # z=0.6 > axial_max


def test_build_predicate_invalid_axis():
    """Invalid axis raises ValueError."""
    cfg = BCConfig(axis="w", mode="axial_plane")
    with pytest.raises(ValueError, match="axis must be x/y/z"):
        build_predicate(cfg)


def test_build_predicate_invalid_mode():
    """Invalid mode raises ValueError."""
    cfg = BCConfig(axis="z", mode="invalid")
    with pytest.raises(ValueError, match="mode must be"):
        build_predicate(cfg)
