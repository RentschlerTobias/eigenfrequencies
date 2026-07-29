"""Field-parity guard: committed schema must stay in sync with dataclasses.

If a field is added to or removed from a dataclass without regenerating the
schema, this test fails.  Regeneration is one command:

    uv run python -m eigenfrequencies.schema --out schema/
"""

import dataclasses
import json
import os
from dataclasses import fields

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
    RunConfig,
    SolverConfig,
    WetModeConfig,
)
from eigenfrequencies.schema import generate_schema

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
_SCHEMA_PATH = os.path.join(_REPO_ROOT, "schema", "eigenfrequencies-config.schema.json")

_SUB_CONFIG_CLASSES = [
    ("MaterialConfig", MaterialConfig),
    ("BCConfig", BCConfig),
    ("MeshConfig", MeshConfig),
    ("SolverConfig", SolverConfig),
    ("DesignConfig", DesignConfig),
    ("OptimizationConfig", OptimizationConfig),
    ("DEConfig", DEConfig),
    ("CFDConfig", CFDConfig),
    ("ObjectiveConfig", ObjectiveConfig),
    ("WetModeConfig", WetModeConfig),
    ("OutputConfig", OutputConfig),
]

_RUNCONFIG_FIELD_MAP = {
    "material": MaterialConfig,
    "bc": BCConfig,
    "mesh": MeshConfig,
    "solver": SolverConfig,
    "design": DesignConfig,
    "optimization": OptimizationConfig,
    "de": DEConfig,
    "cfd": CFDConfig,
    "objective": ObjectiveConfig,
    "wet_mode": WetModeConfig,
    "output": OutputConfig,
}


def test_committed_schema_exists():
    assert os.path.isfile(_SCHEMA_PATH), (
        f"Committed schema not found at {_SCHEMA_PATH}. "
        "Run: uv run python -m eigenfrequencies.schema --out schema/"
    )


def test_schema_parity():
    """Dataclass fields and required sets must match the committed schema."""
    with open(_SCHEMA_PATH) as fh:
        committed = json.load(fh)

    # Top-level RunConfig parity
    run_schema = committed
    expected_run_fields = set(_RUNCONFIG_FIELD_MAP.keys())
    actual_run_fields = set(run_schema.get("properties", {}).keys())
    assert expected_run_fields == actual_run_fields, (
        f"RunConfig field mismatch: dataclass has {sorted(expected_run_fields)}, "
        f"schema has {sorted(actual_run_fields)}"
    )

    expected_run_required = {
        f.name for f in fields(RunConfig)
        if f.default is dataclasses.MISSING and f.default_factory is dataclasses.MISSING
    }
    actual_run_required = set(run_schema.get("required", []))
    assert expected_run_required == actual_run_required, (
        f"RunConfig required-field mismatch: dataclass requires {sorted(expected_run_required)}, "
        f"schema requires {sorted(actual_run_required)}"
    )

    # Sub-config parity
    for field_name, cls in _RUNCONFIG_FIELD_MAP.items():
        cls_schema = run_schema["properties"][field_name]

        expected_fields = {f.name for f in fields(cls)}
        actual_fields = set(cls_schema.get("properties", {}).keys())
        assert expected_fields == actual_fields, (
            f"{cls.__name__} field mismatch: dataclass has {sorted(expected_fields)}, "
            f"schema has {sorted(actual_fields)}"
        )

        expected_required = {
            f.name for f in fields(cls) if f.default is dataclasses.MISSING
        }
        actual_required = set(cls_schema.get("required", []))
        assert expected_required == actual_required, (
            f"{cls.__name__} required-field mismatch: dataclass requires {sorted(expected_required)}, "
            f"schema requires {sorted(actual_required)}"
        )


def test_schema_determinism():
    """Generating twice in the same process must yield identical output."""
    s1 = generate_schema()
    s2 = generate_schema()
    assert s1 == s2


def test_omega_is_readonly():
    """CFDConfig.omega must be marked readOnly in the committed schema."""
    with open(_SCHEMA_PATH) as fh:
        committed = json.load(fh)

    omega_schema = committed["properties"]["cfd"]["properties"]["omega"]
    assert omega_schema.get("readOnly") is True, (
        "CFDConfig.omega must be marked readOnly (computed in __post_init__)"
    )
