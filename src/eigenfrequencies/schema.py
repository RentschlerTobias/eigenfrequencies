"""JSON Schema generator for eigenfrequencies config dataclasses.

Derives schema programmatically from the dataclass tree using only stdlib
``dataclasses``, ``json``, and ``typing``.  Defaults that are not simple
literals (e.g. env-dependent expressions) are omitted so the schema stays
deterministic.
"""

import argparse
import dataclasses
import json
import os
import sys
import typing
from typing import Any, Dict, Optional, Tuple, get_args, get_origin

# We must import the config module *after* sanitising the environment so that
# class-level defaults that read os.environ resolve to their static fallbacks.
_CLEAN_ENV_KEYS = (
    "W_RESONANCE",
    "EVAL_MODE",
    "DESIGN_PRESET",
    "DE_POP_SIZE",
    "DE_MAX_GEN",
    "DE_SEED",
    "DE_MUTATION",
    "DE_CROSSOVER",
    "DE_TOL",
)

# Save and clear env vars before importing config module
_env_backup = {k: os.environ.pop(k) for k in _CLEAN_ENV_KEYS if k in os.environ}
try:
    # Force re-evaluation of config module if already cached
    if "eigenfrequencies.config" in sys.modules:
        import importlib

        importlib.reload(sys.modules["eigenfrequencies.config"])
    else:
        import eigenfrequencies.config  # noqa: F401
finally:
    for k, v in _env_backup.items():
        os.environ[k] = v

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
    "material": ("MaterialConfig", MaterialConfig),
    "bc": ("BCConfig", BCConfig),
    "mesh": ("MeshConfig", MeshConfig),
    "solver": ("SolverConfig", SolverConfig),
    "design": ("DesignConfig", DesignConfig),
    "optimization": ("OptimizationConfig", OptimizationConfig),
    "de": ("DEConfig", DEConfig),
    "cfd": ("CFDConfig", CFDConfig),
    "objective": ("ObjectiveConfig", ObjectiveConfig),
    "wet_mode": ("WetModeConfig", WetModeConfig),
    "output": ("OutputConfig", OutputConfig),
}


def _is_simple_literal(value: Any) -> bool:
    """Return True if *value* is a literal safe to embed as a schema default."""
    if value is None:
        return True
    if isinstance(value, (bool, int, float, str)):
        return True
    if isinstance(value, tuple):
        return all(_is_simple_literal(v) for v in value)
    return False


def _type_to_schema(t: Any) -> Dict[str, Any]:
    """Convert a Python type annotation to a JSON Schema fragment."""
    origin = get_origin(t)
    args = get_args(t)

    # Optional[X] == Union[X, None]
    if origin is typing.Union:
        non_none = [a for a in args if a is not type(None)]
        if len(non_none) == 1 and type(None) in args:
            inner = _type_to_schema(non_none[0])
            if "type" in inner:
                if isinstance(inner["type"], list):
                    if "null" not in inner["type"]:
                        inner["type"] = [*inner["type"], "null"]
                else:
                    inner["type"] = [inner["type"], "null"]
            return inner
        # Complex Union – fall back to permissive string
        return {"type": "string"}

    if origin in (tuple, Tuple):
        if args:
            item_schema = _type_to_schema(args[0])
            return {
                "type": "array",
                "items": item_schema,
                "minItems": len(args),
                "maxItems": len(args),
            }
        return {"type": "array"}

    if t is float:
        return {"type": "number"}
    if t is int:
        return {"type": "integer"}
    if t is str:
        return {"type": "string"}
    if t is bool:
        return {"type": "boolean"}
    if t in (dict, typing.Dict):
        return {"type": "object"}

    return {"type": "string"}


def _field_to_schema(field: dataclasses.Field, cls_name: str) -> Dict[str, Any]:
    """Convert a single dataclass field to a JSON Schema property."""
    schema = _type_to_schema(field.type)

    if field.default is not dataclasses.MISSING:
        if _is_simple_literal(field.default):
            schema["default"] = field.default
            # A default of None on a non-Optional field still means null is accepted
            if field.default is None and "type" in schema:
                if isinstance(schema["type"], list):
                    if "null" not in schema["type"]:
                        schema["type"] = [*schema["type"], "null"]
                else:
                    schema["type"] = [schema["type"], "null"]
        # else: omit default for complex / env-dependent expressions

    # Mark computed fields as readOnly
    if cls_name == "CFDConfig" and field.name == "omega":
        schema["readOnly"] = True

    return schema


def _build_sub_schema(name: str, cls: type) -> Dict[str, Any]:
    """Build JSON Schema for a single sub-config dataclass."""
    cls_schema: Dict[str, Any] = {
        "type": "object",
        "properties": {},
        "required": [],
    }
    for field in dataclasses.fields(cls):
        cls_schema["properties"][field.name] = _field_to_schema(field, name)
        if field.default is dataclasses.MISSING:
            cls_schema["required"].append(field.name)
    return cls_schema


def generate_schema() -> Dict[str, Any]:
    """Generate a deterministic JSON Schema for the RunConfig dataclass tree."""
    # Build sub-config schemas
    sub_schemas: Dict[str, Any] = {}
    for name, cls in _SUB_CONFIG_CLASSES:
        sub_schemas[name] = _build_sub_schema(name, cls)

    # Build RunConfig schema
    run_properties: Dict[str, Any] = {}
    run_required: list = []
    for field_name, (sub_name, sub_cls) in _RUNCONFIG_FIELD_MAP.items():
        run_properties[field_name] = sub_schemas[sub_name]
        if field_name in ("optimization", "cfd"):
            run_required.append(field_name)

    schema: Dict[str, Any] = {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "title": "EigenfrequenciesConfig",
        "description": "Configuration schema for hydraulic turbine runner modal analysis",
        "type": "object",
        "properties": run_properties,
        "required": run_required,
    }

    return schema


def _write_schema(out_dir: str) -> str:
    """Generate schema and write it to *out_dir*.  Return the file path."""
    os.makedirs(out_dir, exist_ok=True)
    schema = generate_schema()
    out_path = os.path.join(out_dir, "eigenfrequencies-config.schema.json")
    with open(out_path, "w") as fh:
        json.dump(schema, fh, indent=2, sort_keys=True)
    return out_path


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate JSON Schema for eigenfrequencies config"
    )
    parser.add_argument(
        "--out", required=True, help="Output directory for schema file"
    )
    args = parser.parse_args()
    out_path = _write_schema(args.out)
    print(f"Schema written to {out_path}")


if __name__ == "__main__":
    main()
