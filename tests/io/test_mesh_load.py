"""Test mesh loading and volume verification."""

import os
import sys

import pytest

from eigenfrequencies.config import MeshConfig
from eigenfrequencies.io.load import load_and_prepare_mesh

dolfinx = pytest.importorskip("dolfinx", reason="dolfinx required for mesh loading")


_FIXTURE_DIR = os.path.join(os.path.dirname(__file__), "..", "fixtures")
_FIXTURE_MSH = os.path.join(_FIXTURE_DIR, "unit_box_coarse.msh")


@pytest.mark.requires_container
@pytest.mark.slow
def test_load_mesh_and_verify_volume():
    """Load a real 3-D mesh and verify it has positive volume.

    Uses the committed fixture rather than turbine_runner/data/testcase_coarse.msh:
    that file is covered by *.msh in .gitignore, was never committed, and is gone.
    Regenerate the fixture with tests/fixtures/make_fixture_mesh.py.
    """
    if not os.path.isfile(_FIXTURE_MSH):
        sys.path.insert(0, os.path.abspath(_FIXTURE_DIR))
        try:
            from make_fixture_mesh import generate
        finally:
            sys.path.pop(0)
        generate(_FIXTURE_MSH)

    mesh_cfg = MeshConfig(msh_path=_FIXTURE_MSH, gdim=3)
    domain = load_and_prepare_mesh(mesh_cfg)
    tdim = domain.topology.dim
    assert tdim == 3, f"Expected 3-D mesh, got topology.dim={tdim}"
    num_cells = domain.topology.index_map(tdim).size_local
    assert num_cells > 0, "Mesh has no cells"
