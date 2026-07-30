"""Tests for ``machine_yaml.py``: loader, validation, and dataclass construction.

All tests are stdlib-only (no dtOO, no dolfinx) and run locally.
"""

import os
import tempfile

import pytest

from eigenfrequencies.adapters.dtoo.machine_yaml import (
    BCTemplate,
    DesignBounds,
    MachineAdapterConfig,
    _validate_axis,
    _validate_design_bounds,
    load_machine_yaml,
)
from eigenfrequencies.config_yaml import ConfigError

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_yaml(text: str) -> str:
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as tmp:
        tmp.write(text)
        return tmp.name


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------

def test_load_minimal_valid_yaml():
    """A minimal valid machine YAML must parse into ``MachineAdapterConfig``."""
    path = _write_yaml(
        """
name: tistos
case_dir: /dtOO/test/tistos
state: templateState
mech_volume: ruWithRounding_mechMesh
adjust_plugin: ru_adjustPlugin
design:
  cV_ru_bladeLength_0.5:
    min: 0.6
    max: 1.0
"""
    )
    try:
        cfg = load_machine_yaml(path)
        assert isinstance(cfg, MachineAdapterConfig)
        assert cfg.name == "tistos"
        assert cfg.case_dir == "/dtOO/test/tistos"
        assert cfg.state == "templateState"
        assert cfg.mech_volume == "ruWithRounding_mechMesh"
        assert cfg.adjust_plugin == "ru_adjustPlugin"
        assert cfg.mesh_scale_factor == 1.0
        assert cfg.bc_template == BCTemplate("hub_clamp")
        assert cfg.axis == "auto"
        assert cfg.design == {
            "cV_ru_bladeLength_0.5": DesignBounds(min=0.6, max=1.0),
        }
    finally:
        os.unlink(path)


def test_load_full_yaml():
    """A fully-populated YAML with all optional fields must parse correctly."""
    path = _write_yaml(
        """
name: tistos_full
case_dir: /dtOO/test/tistos
state: templateState
mech_volume: ruWithRounding_mechMesh
adjust_plugin: ru_adjustPlugin
mesh_scale_factor: 0.001
bc_template:
  type: foil_clamp
  params:
    axis: z
    plane_value: 0.0
axis:
  - 0.0
  - 0.0
  - 1.0
design:
  cV_ru_bladeLength_0.5:
    min: 0.6
    max: 1.0
  cV_ru_t_mid_a_0.5:
    min: 0.005
    max: 0.06
"""
    )
    try:
        cfg = load_machine_yaml(path)
        assert cfg.mesh_scale_factor == 0.001
        assert cfg.bc_template == BCTemplate("foil_clamp", {"axis": "z", "plane_value": 0.0})
        assert cfg.axis == [0.0, 0.0, 1.0]
        assert len(cfg.design) == 2
    finally:
        os.unlink(path)


def test_bc_template_string_shorthand():
    """``bc_template: free_free`` (plain string) must be accepted."""
    path = _write_yaml(
        """
name: free_test
case_dir: /tmp
state: s
mech_volume: v
adjust_plugin: p
design:
  x:
    min: 0
    max: 1
bc_template: free_free
"""
    )
    try:
        cfg = load_machine_yaml(path)
        assert cfg.bc_template == BCTemplate("free_free")
    finally:
        os.unlink(path)


# ---------------------------------------------------------------------------
# Unknown key validation
# ---------------------------------------------------------------------------

def test_unknown_key_at_root_raises():
    """A typo at the root level must raise ``ConfigError``."""
    path = _write_yaml(
        """
name: tistos
case_dir: /dtOO/test/tistos
state: templateState
mech_volume: ruWithRounding_mechMesh
adjust_plugin: ru_adjustPlugin
extra_key: 123
design:
  x:
    min: 0
    max: 1
"""
    )
    try:
        with pytest.raises(ConfigError) as exc_info:
            load_machine_yaml(path)
        assert "extra_key" in str(exc_info.value)
        assert "Unknown key" in str(exc_info.value)
    finally:
        os.unlink(path)


def test_unknown_key_in_design_raises():
    """An unknown key inside a design-parameter block must raise ``ConfigError``."""
    path = _write_yaml(
        """
name: tistos
case_dir: /dtOO/test/tistos
state: templateState
mech_volume: ruWithRounding_mechMesh
adjust_plugin: ru_adjustPlugin
design:
  cV_ru_bladeLength_0.5:
    min: 0.6
    max: 1.0
    initial: 0.75
"""
    )
    try:
        with pytest.raises(ConfigError) as exc_info:
            load_machine_yaml(path)
        err = str(exc_info.value)
        assert "initial" in err
        assert "Unknown key" in err
        assert "design.cV_ru_bladeLength_0.5" in err
    finally:
        os.unlink(path)


def test_unknown_key_in_bc_template_raises():
    """An unknown key inside ``bc_template`` must raise ``ConfigError``."""
    path = _write_yaml(
        """
name: tistos
case_dir: /dtOO/test/tistos
state: templateState
mech_volume: ruWithRounding_mechMesh
adjust_plugin: ru_adjustPlugin
design:
  x:
    min: 0
    max: 1
bc_template:
  type: hub_clamp
  extra: 1
"""
    )
    try:
        with pytest.raises(ConfigError) as exc_info:
            load_machine_yaml(path)
        assert "extra" in str(exc_info.value)
    finally:
        os.unlink(path)


# ---------------------------------------------------------------------------
# Missing required field validation
# ---------------------------------------------------------------------------

def test_missing_required_field_raises():
    """Omitting a required field like ``mech_volume`` must raise ``ConfigError``."""
    path = _write_yaml(
        """
name: tistos
case_dir: /dtOO/test/tistos
state: templateState
adjust_plugin: ru_adjustPlugin
design:
  x:
    min: 0
    max: 1
"""
    )
    try:
        with pytest.raises(ConfigError) as exc_info:
            load_machine_yaml(path)
        assert "mech_volume" in str(exc_info.value)
        assert "Missing required field" in str(exc_info.value)
    finally:
        os.unlink(path)


# ---------------------------------------------------------------------------
# Design-bounds validation
# ---------------------------------------------------------------------------

def test_design_min_greater_than_max_raises():
    """``min > max`` in a design parameter must raise ``ConfigError``."""
    path = _write_yaml(
        """
name: tistos
case_dir: /dtOO/test/tistos
state: templateState
mech_volume: ruWithRounding_mechMesh
adjust_plugin: ru_adjustPlugin
design:
  cV_x:
    min: 1.0
    max: 0.0
"""
    )
    try:
        with pytest.raises(ConfigError) as exc_info:
            load_machine_yaml(path)
        err = str(exc_info.value)
        assert "cV_x" in err
        assert "min (1.0) > max (0.0)" in err
    finally:
        os.unlink(path)


def test_validate_design_bounds_helper():
    """The internal helper must catch min>max and unknown keys."""
    with pytest.raises(ConfigError):
        _validate_design_bounds({"x": {"min": 1, "max": 0}}, path="design")

    with pytest.raises(ConfigError):
        _validate_design_bounds({"x": {"min": 0}}, path="design")

    with pytest.raises(ConfigError):
        _validate_design_bounds({"x": {"min": 0, "max": 1, "extra": 2}}, path="design")


# ---------------------------------------------------------------------------
# Axis validation
# ---------------------------------------------------------------------------

def test_axis_auto_accepted():
    """``"auto"`` is the default and must be accepted."""
    path = _write_yaml(
        """
name: tistos
case_dir: /dtOO/test/tistos
state: templateState
mech_volume: ruWithRounding_mechMesh
adjust_plugin: ru_adjustPlugin
design:
  x:
    min: 0
    max: 1
axis: auto
"""
    )
    try:
        cfg = load_machine_yaml(path)
        assert cfg.axis == "auto"
    finally:
        os.unlink(path)


def test_axis_explicit_vector_accepted():
    """An explicit 3-vector must be accepted and normalised to floats."""
    path = _write_yaml(
        """
name: tistos
case_dir: /dtOO/test/tistos
state: templateState
mech_volume: ruWithRounding_mechMesh
adjust_plugin: ru_adjustPlugin
design:
  x:
    min: 0
    max: 1
axis: [0, 0, 1]
"""
    )
    try:
        cfg = load_machine_yaml(path)
        assert cfg.axis == [0.0, 0.0, 1.0]
    finally:
        os.unlink(path)


def test_axis_invalid_string_raises():
    """An axis string other than ``"auto"`` must raise ``ConfigError``."""
    path = _write_yaml(
        """
name: tistos
case_dir: /dtOO/test/tistos
state: templateState
mech_volume: ruWithRounding_mechMesh
adjust_plugin: ru_adjustPlugin
design:
  x:
    min: 0
    max: 1
axis: z
"""
    )
    try:
        with pytest.raises(ConfigError) as exc_info:
            load_machine_yaml(path)
        assert "auto" in str(exc_info.value)
    finally:
        os.unlink(path)


def test_axis_wrong_length_raises():
    """A vector with != 3 components must raise ``ConfigError``."""
    path = _write_yaml(
        """
name: tistos
case_dir: /dtOO/test/tistos
state: templateState
mech_volume: ruWithRounding_mechMesh
adjust_plugin: ru_adjustPlugin
design:
  x:
    min: 0
    max: 1
axis: [0, 1]
"""
    )
    try:
        with pytest.raises(ConfigError) as exc_info:
            load_machine_yaml(path)
        assert "3 components" in str(exc_info.value)
    finally:
        os.unlink(path)


def test_validate_axis_helper():
    """Internal axis validator coverage."""
    assert _validate_axis("auto") == "auto"
    assert _validate_axis([0, 0, 1]) == [0.0, 0.0, 1.0]

    with pytest.raises(ConfigError):
        _validate_axis("z")
    with pytest.raises(ConfigError):
        _validate_axis([0, 1])
    with pytest.raises(ConfigError):
        _validate_axis({"x": 0})


# ---------------------------------------------------------------------------
# YAML root type guard
# ---------------------------------------------------------------------------

def test_non_dict_root_raises():
    """A YAML file containing a bare list must raise ``ConfigError``."""
    path = _write_yaml("- item1\n- item2\n")
    try:
        with pytest.raises(ConfigError) as exc_info:
            load_machine_yaml(path)
        assert "mapping" in str(exc_info.value)
    finally:
        os.unlink(path)
