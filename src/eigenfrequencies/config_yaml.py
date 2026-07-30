"""YAML config loader / dumper with strict validation.

``load_config`` turns a YAML file into a ``RunConfig`` dataclass tree,
rejecting unknown keys and missing required fields.
``dump_config`` writes a ``RunConfig`` back to deterministic, human-readable
YAML.
"""

import dataclasses
from dataclasses import fields, is_dataclass
from pathlib import Path
from typing import Any, Dict, Optional, Tuple, Type, get_type_hints

import yaml

from eigenfrequencies.config import RunConfig


class ConfigError(ValueError):
    """Raised when YAML config violates the strict schema."""

    pass


def _get_dataclass_fields(cls: Type) -> Dict[str, Any]:
    """Return {field_name: field_type} for a dataclass."""
    return {f.name: f for f in fields(cls)}


def _validate_keys(
    data: dict,
    cls: Type,
    path: str = "",
) -> None:
    """Raise ConfigError if *data* contains keys not defined by *cls*.

    Dotted path is included in the error message so the user knows exactly
    where the typo lives.
    """
    expected = set(_get_dataclass_fields(cls).keys())
    actual = set(data.keys())
    unknown = actual - expected
    if unknown:
        dotted = f"{path}." if path else ""
        raise ConfigError(
            f"Unknown key(s) at {dotted}<root>: {sorted(unknown)}"
            if not path
            else f"Unknown key(s) at {path}: {sorted(unknown)}"
        )


def _validate_required_fields(
    data: dict,
    cls: Type,
    path: str = "",
) -> None:
    """Raise ConfigError if any dataclass field without a default is missing.

    The error message lists the missing fields.
    """
    missing = []
    for f in fields(cls):
        if f.name not in data:
            # Field has no default if default is dataclasses.MISSING
            # and default_factory is also MISSING
            if f.default is dataclasses.MISSING and f.default_factory is dataclasses.MISSING:
                missing.append(f.name)
    if missing:
        dotted = f"{path}." if path else ""
        raise ConfigError(
            f"Missing required field(s) at {dotted}<root>: {sorted(missing)}"
            if not path
            else f"Missing required field(s) at {path}: {sorted(missing)}"
        )


def _construct_dataclass(
    data: dict,
    cls: Type,
    path: str = "",
) -> Any:
    """Recursively construct a dataclass instance from a plain dict.

    Steps:
    1. Validate no unknown keys.
    2. Validate no missing required fields.
    3. For each field value that is a dict and whose type is a dataclass,
       recurse.
    4. Call the dataclass constructor.
    """
    if not isinstance(data, dict):
        raise ConfigError(
            f"Expected dict at {path or '<root>'}, got {type(data).__name__}"
        )

    _validate_keys(data, cls, path)
    _validate_required_fields(data, cls, path)

    kwargs: Dict[str, Any] = {}
    field_map = _get_dataclass_fields(cls)

    for key, raw_value in data.items():
        field_info = field_map[key]
        field_type = field_info.type

        # Resolve Optional[T] -> T
        origin = getattr(field_type, "__origin__", None)
        if origin is not None:
            args = getattr(field_type, "__args__", ())
            if origin is Optional and len(args) == 1:
                field_type = args[0]
                origin = getattr(field_type, "__origin__", None)

        # If the field type is a dataclass and the value is a dict, recurse
        if is_dataclass(field_type) and isinstance(raw_value, dict):
            kwargs[key] = _construct_dataclass(
                raw_value, field_type, path=f"{path}.{key}" if path else key
            )
        else:
            kwargs[key] = raw_value

    try:
        return cls(**kwargs)
    except TypeError as exc:
        raise ConfigError(
            f"Failed to construct {cls.__name__} at {path or '<root>'}: {exc}"
        ) from exc


def load_config(path: str | Path) -> RunConfig:
    """Parse a YAML file and return a strictly-validated ``RunConfig``.

    Unknown keys raise ``ConfigError`` naming the dotted path.
    Missing required fields raise ``ConfigError`` listing the fields.
    """
    path = Path(path)
    with open(path, "r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)

    if not isinstance(raw, dict):
        raise ConfigError(
            f"YAML root must be a mapping, got {type(raw).__name__}"
        )

    return _construct_dataclass(raw, RunConfig, path="<root>")


def _dataclass_to_dict(obj: Any) -> Any:
    """Recursively convert a dataclass tree to plain dicts/lists.

    Tuples are converted to lists so YAML represents them naturally.
    """
    if is_dataclass(obj) and not isinstance(obj, type):
        result: Dict[str, Any] = {}
        for f in fields(obj):
            value = getattr(obj, f.name)
            result[f.name] = _dataclass_to_dict(value)
        return result
    if isinstance(obj, tuple):
        return [_dataclass_to_dict(v) for v in obj]
    if isinstance(obj, list):
        return [_dataclass_to_dict(v) for v in obj]
    if isinstance(obj, dict):
        return {k: _dataclass_to_dict(v) for k, v in obj.items()}
    return obj


def dump_config(config: RunConfig, path: str | Path) -> None:
    """Write a ``RunConfig`` to YAML in deterministic, human-readable form.

    Output order follows the dataclass field definition order.
    """
    path = Path(path)
    data = _dataclass_to_dict(config)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        yaml.dump(
            data,
            fh,
            default_flow_style=False,
            sort_keys=False,
            allow_unicode=True,
        )
