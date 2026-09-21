"""Machine presets for modal analysis.

A machine preset carries only modal physics: material, boundary condition
template, rotation axis, mesh scale factor, solver settings and the resonance
band parameters. Design parameters and dtOO case data are not part of this
module -- the calling framework owns them.

Presets live in ``adapters/machines/<name>.yaml`` at the repository root and
can be overridden with the ``EIGENFREQUENCIES_MACHINES_DIR`` environment
variable.
"""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Optional

import yaml

from eigenfrequencies.bc.builders import from_template
from eigenfrequencies.config import (
    BCConfig,
    MaterialConfig,
    MeshConfig,
    SolverConfig,
)
from eigenfrequencies.config_yaml import ConfigError

MACHINES_DIR_ENV = "EIGENFREQUENCIES_MACHINES_DIR"

_REQUIRED_KEYS = {"name", "material", "bc_template", "axis", "solver", "resonance"}
_EXPECTED_KEYS = _REQUIRED_KEYS | {"mesh_scale_factor"}


def machines_dir() -> str:
    """Directory holding the machine YAML files."""
    override = os.environ.get(MACHINES_DIR_ENV)
    if override:
        return override
    return str(Path(__file__).resolve().parents[2] / "adapters" / "machines")


def machine_yaml_path(machine: str) -> str:
    """Path of the YAML file for ``machine`` (does not check existence)."""
    return os.path.join(machines_dir(), f"{machine}.yaml")


@dataclass
class MachineModalPreset:
    """Modal-physics preset for one machine."""

    name: str
    axis: str
    material: MaterialConfig
    bc: BCConfig
    solver: SolverConfig
    resonance: Dict[str, float] = field(default_factory=dict)
    mesh_scale_factor: float = 1.0

    @property
    def mesh(self) -> MeshConfig:
        return MeshConfig(scale_factor=self.mesh_scale_factor)


def _require_mapping(value, key, path):
    if not isinstance(value, dict):
        raise ConfigError(f"{path}: '{key}' must be a mapping, got {type(value).__name__}")
    return value


def load_machine(path_or_name: str) -> MachineModalPreset:
    """Load and validate a machine preset from a YAML path or machine name."""
    path = path_or_name
    if not os.path.isfile(path):
        path = machine_yaml_path(path_or_name)
    if not os.path.isfile(path):
        raise FileNotFoundError(f"machine preset not found: {path}")

    with open(path, "r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    if not isinstance(data, dict):
        raise ConfigError(f"{path}: YAML root must be a mapping")

    unknown = set(data) - _EXPECTED_KEYS
    if unknown:
        raise ConfigError(f"{path}: unknown keys {sorted(unknown)}")
    missing = _REQUIRED_KEYS - set(data)
    if missing:
        raise ConfigError(f"{path}: missing required keys {sorted(missing)}")

    material_data = _require_mapping(data["material"], "material", path)
    material = MaterialConfig(**material_data)

    bc_data = _require_mapping(data["bc_template"], "bc_template", path)
    bc_type = bc_data.get("type")
    if not bc_type:
        raise ConfigError(f"{path}: bc_template requires 'type'")
    bc = from_template(bc_type, bc_data.get("params"))
    # "auto" means the axis is not yet known; leave the template default and let
    # the caller resolve it. An explicit axis overrides the template.
    if data["axis"] != "auto":
        bc.axis = data["axis"]

    solver_data = _require_mapping(data["solver"], "solver", path)
    solver = SolverConfig(**solver_data)

    resonance_data = _require_mapping(data["resonance"], "resonance", path)

    return MachineModalPreset(
        name=data["name"],
        axis=data["axis"],
        material=material,
        bc=bc,
        solver=solver,
        resonance=resonance_data,
        mesh_scale_factor=float(data.get("mesh_scale_factor", 1.0)),
    )
