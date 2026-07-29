"""Test mesh loading and volume verification."""

import os

import pytest

from eigenfrequencies.config import MeshConfig
from eigenfrequencies.io.load import load_and_prepare_mesh

dolfinx = pytest.importorskip("dolfinx", reason="dolfinx required for mesh loading")


@pytest.mark.requires_container
@pytest.mark.slow
def test_load_mesh_and_verify_volume():
    """Load a real 3-D mesh and verify it has positive volume."""
    msh_path = "turbine_runner/data/testcase_coarse.msh"
    assert os.path.isfile(msh_path), f"Mesh file not found: {msh_path}"

    mesh_cfg = MeshConfig(msh_path=msh_path, gdim=3)
    domain = load_and_prepare_mesh(mesh_cfg)
    tdim = domain.topology.dim
    assert tdim == 3, f"Expected 3-D mesh, got topology.dim={tdim}"
    num_cells = domain.topology.index_map(tdim).size_local
    assert num_cells > 0, "Mesh has no cells"
