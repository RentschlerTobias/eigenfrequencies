"""Field-parity guard: committed schema must stay in sync with dataclasses.

If a field is added to or removed from a dataclass without regenerating the
schema, this test fails.  Regeneration is one command:

    uv run python -m eigenfrequencies.schema --out schema/
"""

import dataclasses
import json
import os
from dataclasses import fields

from eigenfrequencies.config import (
    BCConfig,
    MaterialConfig,
    MeshConfig,
    ModalAnalysisConfig,
    OutputConfig,
    ResonanceConfig,
    SolverConfig,
    WetModeConfig,
)
from eigenfrequencies.schema import generate_schema

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
_SCHEMA_PATH = os.path.join(_REPO_ROOT, "schema", "eigenfrequencies-config.schema.json")

_CONFIG_FIELD_MAP = {
    "material": MaterialConfig,
    "bc": BCConfig,
    "mesh": MeshConfig,
    "solver": SolverConfig,
    "resonance": ResonanceConfig,
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

    expected_fields = set(_CONFIG_FIELD_MAP.keys())
    actual_fields = set(committed.get("properties", {}).keys())
    assert expected_fields == actual_fields, (
        f"ModalAnalysisConfig field mismatch: dataclass has {sorted(expected_fields)}, "
        f"schema has {sorted(actual_fields)}"
    )

    expected_required = {
        f.name for f in fields(ModalAnalysisConfig)
        if f.default is dataclasses.MISSING and f.default_factory is dataclasses.MISSING
    }
    actual_required = set(committed.get("required", []))
    assert expected_required == actual_required, (
        f"ModalAnalysisConfig required-field mismatch: dataclass requires "
        f"{sorted(expected_required)}, schema requires {sorted(actual_required)}"
    )

    for field_name, cls in _CONFIG_FIELD_MAP.items():
        cls_schema = committed["properties"][field_name]

        expected = {f.name for f in fields(cls)}
        actual = set(cls_schema.get("properties", {}).keys())
        assert expected == actual, (
            f"{cls.__name__} field mismatch: dataclass has {sorted(expected)}, "
            f"schema has {sorted(actual)}"
        )

        expected_required = {
            f.name for f in fields(cls) if f.default is dataclasses.MISSING
        }
        actual_required = set(cls_schema.get("required", []))
        assert expected_required == actual_required, (
            f"{cls.__name__} required-field mismatch: dataclass requires "
            f"{sorted(expected_required)}, schema requires {sorted(actual_required)}"
        )


def test_schema_determinism():
    """Generating twice in the same process must yield identical output."""
    assert generate_schema() == generate_schema()
