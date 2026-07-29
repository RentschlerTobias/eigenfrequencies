"""Test that zero-volume / non-volume meshes raise MeshVerificationError."""

import os
import tempfile

import gmsh
import pytest

from eigenfrequencies.config import MeshConfig
from eigenfrequencies.io.load import MeshVerificationError, load_and_prepare_mesh

dolfinx = pytest.importorskip("dolfinx", reason="dolfinx required for mesh loading")


def _make_surface_msh(path: str) -> None:
    """Create a gmsh file with only surface elements (no real volume)."""
    gmsh.initialize()
    try:
        gmsh.model.add("surface_only")
        # Simple flat square surface — gmsh cannot create a closed volume from it.
        p1 = gmsh.model.geo.addPoint(0, 0, 0)
        p2 = gmsh.model.geo.addPoint(1, 0, 0)
        p3 = gmsh.model.geo.addPoint(1, 1, 0)
        p4 = gmsh.model.geo.addPoint(0, 1, 0)
        l1 = gmsh.model.geo.addLine(p1, p2)
        l2 = gmsh.model.geo.addLine(p2, p3)
        l3 = gmsh.model.geo.addLine(p3, p4)
        l4 = gmsh.model.geo.addLine(p4, p1)
        ll = gmsh.model.geo.addCurveLoop([l1, l2, l3, l4])
        gmsh.model.geo.addPlaneSurface([ll])
        gmsh.model.geo.synchronize()
        gmsh.model.mesh.generate(2)
        gmsh.write(path)
    finally:
        gmsh.finalize()


@pytest.mark.requires_container
@pytest.mark.slow
def test_zero_volume_mesh_raises():
    """A surface-only mesh must raise MeshVerificationError."""
    with tempfile.TemporaryDirectory() as tmpdir:
        surf_msh = os.path.join(tmpdir, "surface.msh")
        _make_surface_msh(surf_msh)
        mesh_cfg = MeshConfig(msh_path=surf_msh, gdim=3)
        with pytest.raises(MeshVerificationError):
            load_and_prepare_mesh(mesh_cfg)
