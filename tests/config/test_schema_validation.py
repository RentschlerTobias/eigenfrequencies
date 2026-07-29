"""Validate example YAML configs against the generated JSON Schema.

Uses a lightweight stdlib-only validator so no extra dependencies are needed.
"""

import json
import os
from typing import Any, Dict

import pytest
import yaml

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
_SCHEMA_PATH = os.path.join(_REPO_ROOT, "schema", "eigenfrequencies-config.schema.json")
_YAML_DIR = os.path.join(_REPO_ROOT, "examples", "configs")


def _validate_type(instance: Any, schema_type: Any) -> bool:
    """Check whether *instance* matches the JSON Schema *type*."""
    if isinstance(schema_type, list):
        return any(_validate_type(instance, t) for t in schema_type)

    if schema_type == "object":
        return isinstance(instance, dict)
    if schema_type == "array":
        return isinstance(instance, list)
    if schema_type == "string":
        return isinstance(instance, str)
    if schema_type == "integer":
        return isinstance(instance, int) and not isinstance(instance, bool)
    if schema_type == "number":
        return isinstance(instance, (int, float)) and not isinstance(instance, bool)
    if schema_type == "boolean":
        return isinstance(instance, bool)
    if schema_type == "null":
        return instance is None
    return True


def _validate(instance: Any, schema: Dict[str, Any], path: str = "root") -> None:
    """Recursively validate *instance* against a JSON Schema fragment.

    Raises ``ValueError`` with a descriptive message on the first violation.
    """
    if not isinstance(schema, dict):
        return

    # anyOf
    if "anyOf" in schema:
        errors = []
        for sub in schema["anyOf"]:
            try:
                _validate(instance, sub, path)
                return
            except ValueError as exc:
                errors.append(str(exc))
        raise ValueError(
            f"{path}: none of anyOf matched. Errors: {'; '.join(errors)}"
        )

    # Type check
    if "type" in schema:
        if not _validate_type(instance, schema["type"]):
            raise ValueError(
                f"{path}: expected type {schema['type']!r}, got {type(instance).__name__}"
            )

    # Array constraints
    if isinstance(instance, list):
        if "minItems" in schema and len(instance) < schema["minItems"]:
            raise ValueError(
                f"{path}: array length {len(instance)} < minItems {schema['minItems']}"
            )
        if "maxItems" in schema and len(instance) > schema["maxItems"]:
            raise ValueError(
                f"{path}: array length {len(instance)} > maxItems {schema['maxItems']}"
            )
        if "items" in schema:
            for i, item in enumerate(instance):
                _validate(item, schema["items"], f"{path}[{i}]")

    # Object constraints
    if isinstance(instance, dict):
        if "required" in schema:
            for key in schema["required"]:
                if key not in instance:
                    raise ValueError(f"{path}: missing required key {key!r}")
        if "properties" in schema:
            for key, val in instance.items():
                if key in schema["properties"]:
                    _validate(val, schema["properties"][key], f"{path}.{key}")


@pytest.fixture(scope="module")
def schema():
    with open(_SCHEMA_PATH) as fh:
        return json.load(fh)


@pytest.mark.parametrize(
    "yaml_name",
    [
        "beam.yaml",
        "testcase_laval.yaml",
        "tistos.yaml",
        "minimal.yaml",
        "default.yaml",
        "custom.yaml",
    ],
)
def test_example_yaml_validates(schema, yaml_name):
    """Each example YAML must satisfy the committed JSON Schema."""
    yaml_path = os.path.join(_YAML_DIR, yaml_name)
    if not os.path.isfile(yaml_path):
        pytest.skip(f"Example YAML not found: {yaml_path}")

    with open(yaml_path) as fh:
        instance = yaml.safe_load(fh)

    _validate(instance, schema)
