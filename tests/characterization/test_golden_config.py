"""Characterization test: config dataclass roundtrip via JSON.

Freezes the exact instances used by the current tistos run so that future
refactors (e.g. removing a field, changing a default, or altering __post_init__
behaviour) are caught immediately.
"""

import json
import os
from dataclasses import asdict, fields

import pytest

from eigenfrequencies.config import (
    BCConfig,
    CFDConfig,
    DEConfig,
    DesignConfig,
    MaterialConfig,
    MeshConfig,
    ObjectiveConfig,
    OptimizationConfig,
    OutputConfig,
    SolverConfig,
    WetModeConfig,
)

_GOLDEN_DIR = os.path.join(os.path.dirname(__file__), "golden")
_GOLDEN_PATH = os.path.join(_GOLDEN_DIR, "config_roundtrip.json")

_CONFIG_CLASSES = {
    "MaterialConfig": MaterialConfig,
    "BCConfig": BCConfig,
    "MeshConfig": MeshConfig,
    "SolverConfig": SolverConfig,
    "DesignConfig": DesignConfig,
    "OptimizationConfig": OptimizationConfig,
    "DEConfig": DEConfig,
    "CFDConfig": CFDConfig,
    "ObjectiveConfig": ObjectiveConfig,
    "WetModeConfig": WetModeConfig,
    "OutputConfig": OutputConfig,
}


def _deep_eq(a, b):
    """Deep equality that treats tuples and lists as equivalent."""
    if type(a) is not type(b):
        if isinstance(a, (list, tuple)) and isinstance(b, (list, tuple)):
            return len(a) == len(b) and all(_deep_eq(x, y) for x, y in zip(a, b))
        return False
    if isinstance(a, dict):
        return a.keys() == b.keys() and all(_deep_eq(a[k], b[k]) for k in a)
    if isinstance(a, (list, tuple)):
        return len(a) == len(b) and all(_deep_eq(x, y) for x, y in zip(a, b))
    return a == b


def _load_golden():
    with open(_GOLDEN_PATH) as fh:
        return json.load(fh)


def _validate_all_fields_present(cls, data: dict):
    """Raise ValueError if any dataclass field is missing from *data*."""
    expected = {f.name for f in fields(cls)}
    missing = expected - data.keys()
    if missing:
        raise ValueError(
            f"{cls.__name__} missing required field(s): {sorted(missing)}"
        )


@pytest.mark.parametrize("name,cls", list(_CONFIG_CLASSES.items()))
def test_roundtrip_equality(name, cls):
    """Golden JSON -> reconstruct -> asdict must match the golden dict."""
    golden = _load_golden()
    assert name in golden, f"{name} not found in golden JSON"

    _validate_all_fields_present(cls, golden[name])

    kwargs = {}
    if name in ("OptimizationConfig", "CFDConfig"):
        kwargs = {"n_rpm": 72.0}
    original = cls(**kwargs)
    reconstructed = cls(**golden[name])

    assert _deep_eq(asdict(reconstructed), golden[name]), (
        f"{name} reconstruction diverges from golden JSON"
    )
    assert _deep_eq(asdict(original), asdict(reconstructed)), (
        f"{name} roundtrip failed: fresh default != reconstructed"
    )


def test_missing_field_raises():
    """Removing a field from the golden JSON must raise on reconstruction."""
    golden = _load_golden()

    # Pick OptimizationConfig because it is load-bearing (Z_guidevanes, n_rpm,
    # margin_hz, penalty_k) and imported by objective.py / optimize.py.
    target_name = "OptimizationConfig"
    target_cls = _CONFIG_CLASSES[target_name]
    corrupted = dict(golden[target_name])
    removed_key = "margin_hz"
    del corrupted[removed_key]

    with pytest.raises(ValueError) as exc_info:
        _validate_all_fields_present(target_cls, corrupted)
        target_cls(**corrupted)

    err_msg = str(exc_info.value)
    assert "missing required field" in err_msg or removed_key in err_msg, (
        f"Expected missing-field error mentioning '{removed_key}', got: {err_msg}"
    )
