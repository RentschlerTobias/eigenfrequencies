"""Tests for ``adapter.py``: high-level ``DtooAdapter`` class.

All tests are stdlib-only (no dtOO, no dolfinx) and run locally.
The dtOO-dependent ``export_mesh`` path is exercised via mocking.
"""

import os
import tempfile
from unittest.mock import patch

import pytest

from eigenfrequencies.adapters.dtoo.adapter import DtooAdapter
from eigenfrequencies.adapters.dtoo.machine_yaml import (
    BCTemplate,
    MachineAdapterConfig,
)
from eigenfrequencies.bc.builders import clamp, foil_clamp, free_free
from eigenfrequencies.config import BCConfig


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_yaml(text: str) -> str:
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as tmp:
        tmp.write(text)
        return tmp.name


def _minimal_yaml() -> str:
    return _write_yaml(
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


# ---------------------------------------------------------------------------
# Importability
# ---------------------------------------------------------------------------

def test_adapter_importable_without_dtoo():
    """``DtooAdapter`` must be importable when dtOO is absent."""
    # The import at module level already succeeded (this file imported it).
    # Double-check by re-importing the class.
    from eigenfrequencies.adapters.dtoo.adapter import DtooAdapter
    assert DtooAdapter is not None


# ---------------------------------------------------------------------------
# BC template resolution
# ---------------------------------------------------------------------------

def test_bc_hub_clamp():
    """``bc()`` for ``hub_clamp`` template must return a radius-band ``BCConfig``."""
    path = _write_yaml(
        """
name: tistos
case_dir: /dtOO/test/tistos
state: templateState
mech_volume: ruWithRounding_mechMesh
adjust_plugin: ru_adjustPlugin
bc_template:
  type: hub_clamp
  params:
    axis: z
    hub_radius: 0.2
design:
  x:
    min: 0
    max: 1
"""
    )
    try:
        adapter = DtooAdapter(path)
        bc = adapter.bc()
        assert isinstance(bc, BCConfig)
        assert bc.mode == "radius_band"
        assert bc.axis == "z"
        assert bc.hub_radius == 0.2
    finally:
        os.unlink(path)


def test_bc_foil_clamp():
    """``bc()`` for ``foil_clamp`` template must return an axial-plane ``BCConfig``."""
    path = _write_yaml(
        """
name: tistos
case_dir: /dtOO/test/tistos
state: templateState
mech_volume: ruWithRounding_mechMesh
adjust_plugin: ru_adjustPlugin
bc_template:
  type: foil_clamp
  params:
    axis: z
    plane_value: 0.0
design:
  x:
    min: 0
    max: 1
"""
    )
    try:
        adapter = DtooAdapter(path)
        bc = adapter.bc()
        assert bc.mode == "axial_plane"
        assert bc.plane_value == 0.0
    finally:
        os.unlink(path)


def test_bc_free_free():
    """``bc()`` for ``free_free`` template must return a free ``BCConfig``."""
    path = _write_yaml(
        """
name: tistos
case_dir: /dtOO/test/tistos
state: templateState
mech_volume: ruWithRounding_mechMesh
adjust_plugin: ru_adjustPlugin
bc_template: free_free
design:
  x:
    min: 0
    max: 1
"""
    )
    try:
        adapter = DtooAdapter(path)
        bc = adapter.bc()
        assert bc.mode == "free"
    finally:
        os.unlink(path)


def test_bc_unknown_template_raises():
    """``bc()`` with an unknown template type must raise ``ValueError``."""
    path = _write_yaml(
        """
name: tistos
case_dir: /dtOO/test/tistos
state: templateState
mech_volume: ruWithRounding_mechMesh
adjust_plugin: ru_adjustPlugin
bc_template:
  type: magic_clamp
design:
  x:
    min: 0
    max: 1
"""
    )
    try:
        adapter = DtooAdapter(path)
        with pytest.raises(ValueError) as exc_info:
            adapter.bc()
        assert "magic_clamp" in str(exc_info.value)
    finally:
        os.unlink(path)


# ---------------------------------------------------------------------------
# Design bounds
# ---------------------------------------------------------------------------

def test_design_bounds():
    """``design_bounds()`` must return ``{label: (min, max)}``."""
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
  cV_ru_t_mid_a_0.5:
    min: 0.005
    max: 0.06
"""
    )
    try:
        adapter = DtooAdapter(path)
        bounds = adapter.design_bounds()
        assert bounds == {
            "cV_ru_bladeLength_0.5": (0.6, 1.0),
            "cV_ru_t_mid_a_0.5": (0.005, 0.06),
        }
    finally:
        os.unlink(path)


# ---------------------------------------------------------------------------
# Axis property
# ---------------------------------------------------------------------------

def test_axis_auto():
    """Default axis is ``"auto"``."""
    path = _minimal_yaml()
    try:
        adapter = DtooAdapter(path)
        assert adapter.axis == "auto"
    finally:
        os.unlink(path)


def test_axis_explicit():
    """An explicit axis vector is exposed via the property."""
    path = _write_yaml(
        """
name: tistos
case_dir: /dtOO/test/tistos
state: templateState
mech_volume: ruWithRounding_mechMesh
adjust_plugin: ru_adjustPlugin
axis: [0.0, 1.0, 0.0]
design:
  x:
    min: 0
    max: 1
"""
    )
    try:
        adapter = DtooAdapter(path)
        assert adapter.axis == [0.0, 1.0, 0.0]
    finally:
        os.unlink(path)


# ---------------------------------------------------------------------------
# export_mesh (mocked dtOO path)
# ---------------------------------------------------------------------------

def test_export_mesh_calls_run_dtoo_export():
    """``export_mesh`` must delegate to ``run_dtoo_export`` and return its path."""
    path = _minimal_yaml()
    try:
        adapter = DtooAdapter(path)
        design = {"cV_ru_bladeLength_0.5": 0.75}

        with patch(
            "eigenfrequencies.adapters.dtoo.export.run_dtoo_export",
            return_value="/tmp/fake.msh",
        ) as mock_export:
            result = adapter.export_mesh(design)

        mock_export.assert_called_once()
        assert result == "/tmp/fake.msh"
        # Verify the machine config and design values were forwarded.
        call_args = mock_export.call_args
        assert call_args.args[0] == adapter.config
        assert call_args.args[1] == design
    finally:
        os.unlink(path)


def test_export_mesh_without_dtoo_raises_import_error():
    """When dtOO is absent, ``export_mesh`` must raise ``ImportError``."""
    path = _minimal_yaml()
    try:
        adapter = DtooAdapter(path)
        # Force the lazy import to fail by making dtOOPythonSWIG unavailable.
        with patch.dict("sys.modules", {"dtOOPythonSWIG": None}):
            with pytest.raises((ImportError, ModuleNotFoundError)):
                adapter.export_mesh({})
    finally:
        os.unlink(path)
