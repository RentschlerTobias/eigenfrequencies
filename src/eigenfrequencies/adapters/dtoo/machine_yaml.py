"""Machine YAML loader and ``MachineAdapterConfig`` dataclass.

The machine YAML describes a dtOO parametric geometry case: case directory,
state name, mechanical volume label, design-parameter bounds, and boundary-
condition template.  It is the single source of truth consumed by the
``DtooAdapter`` high-level class.
"""

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import yaml

from eigenfrequencies.config_yaml import ConfigError


@dataclass
class DesignBounds:
    """Per-design-parameter bounds."""

    min: float
    max: float


@dataclass
class BCTemplate:
    """Boundary-condition template for the exported mesh.

    Attributes:
        type: One of ``hub_clamp``, ``foil_clamp``, ``free_free``.
        params: Template-specific keyword arguments forwarded to the BC builder.
    """

    type: str
    params: dict = field(default_factory=dict)


@dataclass
class MachineAdapterConfig:
    """dtOO machine adapter configuration.

    Attributes:
        name: Human-readable machine identifier.
        case_dir: Absolute or relative path to the dtOO case directory
            (must contain ``machine.xml`` + ``machineSave.xml`` + ``xml/``).
        state: dtOO state name to load (e.g. ``templateState``).
        mech_volume: Bounded-volume label for the structural mesh
            (e.g. ``ruWithRounding_mechMesh``).
        adjust_plugin: dtPlugin label that finalises the geometry
            (e.g. ``ru_adjustDomain``).
        design: Mapping ``{label: {min: float, max: float}}`` exposing the
            parametric degrees of freedom to the optimizer.
        mesh_scale_factor: Linear scale factor applied to the exported mesh
            coordinates to recover physical units.  Default ``1.0`` means no
            scaling (the dtOO mesh is already in physical units).
        bc_template: Boundary-condition template describing how the mesh is
            constrained after export.
        axis: Rotation axis.  ``"auto"`` lets the adapter discover the axis
            from the mesh bounding box (longest span).  An explicit 3-vector
            ``[x, y, z]`` is used directly.
    """

    name: str
    case_dir: str
    state: str
    mech_volume: str
    adjust_plugin: str
    design: Dict[str, DesignBounds]
    mesh_scale_factor: float = 1.0
    bc_template: BCTemplate = field(default_factory=lambda: BCTemplate("hub_clamp"))
    axis: Union[str, List[float]] = "auto"


def _validate_design_bounds(design: dict, path: str = "design") -> None:
    """Raise ``ConfigError`` if any design parameter has ``min > max``."""
    for label, bounds in design.items():
        if not isinstance(bounds, dict):
            raise ConfigError(
                f"Expected dict at {path}.{label}, got {type(bounds).__name__}"
            )
        unknown = set(bounds.keys()) - {"min", "max"}
        if unknown:
            raise ConfigError(
                f"Unknown key(s) at {path}.{label}: {sorted(unknown)}"
            )
        if "min" not in bounds or "max" not in bounds:
            raise ConfigError(
                f"Missing required field(s) at {path}.{label}: "
                f"{sorted({'min', 'max'} - set(bounds.keys()))}"
            )
        min_v = float(bounds["min"])
        max_v = float(bounds["max"])
        if min_v > max_v:
            raise ConfigError(
                f"Invalid bounds at {path}.{label}: min ({min_v}) > max ({max_v})"
            )


def _construct_design_bounds(raw: dict, path: str = "design") -> Dict[str, DesignBounds]:
    """Turn a plain ``{label: {min: v, max: v}}`` dict into typed ``DesignBounds``."""
    _validate_design_bounds(raw, path)
    return {
        label: DesignBounds(min=float(bounds["min"]), max=float(bounds["max"]))
        for label, bounds in raw.items()
    }


def _construct_bc_template(raw: Any, path: str = "bc_template") -> BCTemplate:
    """Build a ``BCTemplate`` from a dict or a plain string shorthand."""
    if isinstance(raw, str):
        return BCTemplate(type=raw)
    if not isinstance(raw, dict):
        raise ConfigError(
            f"Expected dict or str at {path}, got {type(raw).__name__}"
        )
    unknown = set(raw.keys()) - {"type", "params"}
    if unknown:
        raise ConfigError(f"Unknown key(s) at {path}: {sorted(unknown)}")
    if "type" not in raw:
        raise ConfigError(f"Missing required field 'type' at {path}")
    return BCTemplate(
        type=raw["type"],
        params=raw.get("params", {}),
    )


def _validate_axis(raw: Any, path: str = "axis") -> Union[str, List[float]]:
    """Validate the ``axis`` field: ``"auto"`` or an explicit 3-vector."""
    if isinstance(raw, str):
        if raw != "auto":
            raise ConfigError(
                f"Invalid axis at {path}: expected 'auto' or a 3-vector, got {raw!r}"
            )
        return raw
    if isinstance(raw, list):
        if len(raw) != 3:
            raise ConfigError(
                f"Invalid axis at {path}: expected 3 components, got {len(raw)}"
            )
        try:
            return [float(v) for v in raw]
        except (TypeError, ValueError) as exc:
            raise ConfigError(
                f"Invalid axis at {path}: all components must be numeric ({exc})"
            ) from exc
    raise ConfigError(
        f"Invalid axis at {path}: expected 'auto' or a 3-vector, got {type(raw).__name__}"
    )


def load_machine_yaml(path: str | Path) -> MachineAdapterConfig:
    """Parse a machine YAML and return a strictly-validated ``MachineAdapterConfig``.

    Unknown keys at any level raise ``ConfigError`` with a dotted path.
    Design-parameter bounds with ``min > max`` raise ``ConfigError``.
    """
    path = Path(path)
    with open(path, "r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)

    if not isinstance(raw, dict):
        raise ConfigError(
            f"YAML root must be a mapping, got {type(raw).__name__}"
        )

    expected_keys = {
        "name",
        "case_dir",
        "state",
        "mech_volume",
        "adjust_plugin",
        "design",
        "mesh_scale_factor",
        "bc_template",
        "axis",
    }
    unknown = set(raw.keys()) - expected_keys
    if unknown:
        raise ConfigError(
            f"Unknown key(s) at <root>: {sorted(unknown)}"
        )

    required = {"name", "case_dir", "state", "mech_volume", "adjust_plugin", "design"}
    missing = required - set(raw.keys())
    if missing:
        raise ConfigError(
            f"Missing required field(s) at <root>: {sorted(missing)}"
        )

    kwargs: Dict[str, Any] = {}
    kwargs["name"] = raw["name"]
    kwargs["case_dir"] = os.path.expanduser(raw["case_dir"])
    kwargs["state"] = raw["state"]
    kwargs["mech_volume"] = raw["mech_volume"]
    kwargs["adjust_plugin"] = raw["adjust_plugin"]
    kwargs["design"] = _construct_design_bounds(raw["design"])
    kwargs["mesh_scale_factor"] = float(raw.get("mesh_scale_factor", 1.0))
    kwargs["bc_template"] = _construct_bc_template(raw.get("bc_template", "hub_clamp"))
    kwargs["axis"] = _validate_axis(raw.get("axis", "auto"))

    return MachineAdapterConfig(**kwargs)
