"""STAGE 2a: load the dtOO mesh, verify it is a 3-D volume, fallback if not.

Runs in the fenicsx container. The expected path is trivial: the dtOO
``ruWithRounding_mechMesh`` export already contains 3-D volume cells (tet, second
order), so the mesh is returned as-is. The volume-meshing fallback only fires
when the input is surface-only.

Also exposes ``inspect_mesh`` / a ``__main__`` diagnostic to discover the
rotation axis and hub location before setting ``BCConfig`` (see README).
"""

import numpy as np
from mpi4py import MPI

from config import MeshConfig


def _read_msh(msh_path: str, gdim: int):
    """Read a gmsh .msh into a dolfinx mesh (beam pattern, solver.py:31-34)."""
    from dolfinx.io import gmsh as dgmsh

    mesh_data = dgmsh.read_from_msh(msh_path, MPI.COMM_WORLD, rank=0, gdim=gdim)
    return mesh_data.mesh


def _has_volume_entities(msh_path: str) -> bool:
    """Check via gmsh whether the file actually contains 3-D entities."""
    import gmsh

    gmsh.initialize()
    try:
        gmsh.open(msh_path)
        return len(gmsh.model.getEntities(3)) > 0
    finally:
        gmsh.finalize()


def _volume_mesh_from_cad(step_path: str, element_size: float, out_msh: str) -> str:
    """Fallback A: mesh a 3-D volume from a STEP/BREP CAD file (gmsh OCC).

    Mirrors the OCC usage in ``demo/beam/geometry.py``.
    """
    import gmsh

    gmsh.initialize()
    try:
        gmsh.option.setNumber("Mesh.Algorithm", 6)
        gmsh.model.add("runner_from_cad")
        gmsh.model.occ.importShapes(step_path)
        gmsh.model.occ.synchronize()
        field = gmsh.model.mesh.field.add("MathEval")
        gmsh.model.mesh.field.setString(field, "F", str(element_size))
        gmsh.model.mesh.field.setAsBackgroundMesh(field)
        gmsh.model.mesh.generate(3)
        gmsh.write(out_msh)
    finally:
        gmsh.finalize()
    return out_msh


def _volume_mesh_from_surface(surf_msh: str, element_size: float, out_msh: str) -> str:
    """Fallback B: build a volume from a closed surface mesh.

    Loads the surface, wraps the closed surface loop into a volume, and meshes
    it. Less robust than the CAD path; used only when no STEP/BREP is available.
    """
    import gmsh

    gmsh.initialize()
    try:
        gmsh.option.setNumber("Mesh.Algorithm", 6)
        gmsh.open(surf_msh)
        surfaces = [tag for (dim, tag) in gmsh.model.getEntities(2)]
        if not surfaces:
            raise RuntimeError(f"No surfaces found in {surf_msh}; cannot build a volume.")
        loop = gmsh.model.geo.addSurfaceLoop(surfaces)
        gmsh.model.geo.addVolume([loop])
        gmsh.model.geo.synchronize()
        field = gmsh.model.mesh.field.add("MathEval")
        gmsh.model.mesh.field.setString(field, "F", str(element_size))
        gmsh.model.mesh.field.setAsBackgroundMesh(field)
        gmsh.model.mesh.generate(3)
        gmsh.write(out_msh)
    finally:
        gmsh.finalize()
    return out_msh


def load_and_prepare_mesh(mesh_cfg: MeshConfig):
    """Return a 3-D dolfinx volume mesh, running the fallback only if needed."""
    domain = _read_msh(mesh_cfg.msh_path, mesh_cfg.gdim)
    tdim = domain.topology.dim
    print(f"[mesh_prep] read {mesh_cfg.msh_path}: topology.dim={tdim}, "
          f"cells={domain.topology.index_map(tdim).size_local}")

    if tdim == 3 and not mesh_cfg.force_volume_remesh:
        return domain

    # Volume missing (surface-only mesh) or remesh forced.
    reason = "force_volume_remesh" if tdim == 3 else f"tdim={tdim} (no volume cells)"
    print(f"[mesh_prep] volume-meshing fallback triggered ({reason})")
    out_msh = mesh_cfg.msh_path.replace(".msh", "_volume.msh")

    if mesh_cfg.step_path:
        print(f"[mesh_prep] meshing volume from CAD {mesh_cfg.step_path}")
        _volume_mesh_from_cad(mesh_cfg.step_path, mesh_cfg.fallback_element_size, out_msh)
    else:
        print(f"[mesh_prep] meshing volume from surface {mesh_cfg.msh_path}")
        _volume_mesh_from_surface(mesh_cfg.msh_path, mesh_cfg.fallback_element_size, out_msh)

    domain = _read_msh(out_msh, mesh_cfg.gdim)
    if domain.topology.dim != 3:
        raise RuntimeError(f"Fallback failed to produce a 3-D volume mesh: {out_msh}")
    return domain


def inspect_mesh(mesh_cfg: MeshConfig) -> None:
    """Axis-discovery diagnostic: print the coordinate bbox and per-axis spread.

    Run this once after the first dtOO export to identify the rotation axis and
    hub location, then set BCConfig accordingly (do NOT assume x=0 like the beam).
    """
    domain = _read_msh(mesh_cfg.msh_path, mesh_cfg.gdim)
    x = domain.geometry.x
    print("=" * 60)
    print("Mesh axis-discovery diagnostic")
    print("=" * 60)
    print(f"file:          {mesh_cfg.msh_path}")
    print(f"topology.dim:  {domain.topology.dim}")
    print(f"num nodes:     {x.shape[0]}")
    for i, name in enumerate("xyz"):
        col = x[:, i]
        print(f"  {name}: min={col.min():+.4f}  max={col.max():+.4f}  "
              f"span={col.max() - col.min():.4f}")
    print("Hint: the rotation axis is usually the longest span; the hub bore is")
    print("near the axis at one axial end. Set BCConfig.axis / hub_radius / "
          "axial_min / axial_max from these ranges.")


if __name__ == "__main__":
    inspect_mesh(MeshConfig())
