"""Convert the experimental test-case STL surface into a 3-D volume mesh.

Runs in the fenicsx container (gmsh). The STL
(``TestCaseGeomertyMesh.stl``, exported from ANSYS Mechanical) is watertight,
so the geo kernel can wrap its surface entities directly in a surface loop +
volume; gmsh then tet-meshes only the interior while the STL triangulation is
kept as the boundary mesh. (The classifySurfaces/createGeometry
reparametrization path fails on this STL: "Wrong topology of boundary mesh for
parametrization" -- the direct path avoids it entirely.)

Usage (container, from turbine_runner/):
    python3 stl_to_msh.py                      # defaults
    TESTCASE_ELEMENT_SIZE=0.003 python3 stl_to_msh.py
"""

import os

_HERE = os.path.dirname(os.path.abspath(__file__))

DEFAULT_STL = os.path.join(_HERE, "..", "TestCaseGeomertyMesh.stl")
DEFAULT_MSH = os.path.join(_HERE, "data", "testcase_volume.msh")


def stl_to_volume_msh(stl_path: str, out_msh: str,
                      element_size: float = 0.004,
                      order: int = 1) -> str:
    """Build a tet volume mesh from a closed STL surface; return out_msh.

    element_size targets the volume interior; the boundary keeps the STL
    triangulation, so the effective surface resolution is the STL's own.
    """
    import gmsh

    if not os.path.isfile(stl_path):
        raise FileNotFoundError(f"STL not found: {stl_path}")

    gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 1)
        gmsh.option.setNumber("Mesh.Algorithm", 6)    # Frontal-Delaunay (2D)
        gmsh.option.setNumber("Mesh.Algorithm3D", 1)  # Delaunay (3D)
        gmsh.model.add("testcase")

        print(f"[stl_to_msh] importing {stl_path}")
        gmsh.merge(stl_path)

        surfaces = [tag for (dim, tag) in gmsh.model.getEntities(2)]
        if not surfaces:
            raise RuntimeError(f"No surfaces found in {stl_path}; cannot build a volume.")
        if gmsh.model.getEntities(3):
            raise RuntimeError(f"{stl_path} already contains volume entities; "
                               "expected a pure surface STL.")
        print(f"[stl_to_msh] {len(surfaces)} discrete surface(s) -> surface loop + volume")
        loop = gmsh.model.geo.addSurfaceLoop(surfaces)
        volume = gmsh.model.geo.addVolume([loop])
        gmsh.model.geo.synchronize()
        # dolfinx.io.gmsh.read_from_msh requires at least one physical group.
        gmsh.model.addPhysicalGroup(3, [volume], name="domain")

        # Constant target size; ignore the STL vertex sizes so the field dominates.
        field = gmsh.model.mesh.field.add("MathEval")
        gmsh.model.mesh.field.setString(field, "F", str(element_size))
        gmsh.model.mesh.field.setAsBackgroundMesh(field)
        gmsh.option.setNumber("Mesh.MeshSizeFromPoints", 0)
        gmsh.option.setNumber("Mesh.MeshSizeFromCurvature", 0)
        gmsh.option.setNumber("Mesh.MeshSizeExtendFromBoundary", 0)

        print(f"[stl_to_msh] meshing volume (target size {element_size} m, order {order})")
        gmsh.model.mesh.generate(3)
        if order == 2:
            gmsh.model.mesh.setOrder(2)

        os.makedirs(os.path.dirname(out_msh), exist_ok=True)
        gmsh.write(out_msh)
    finally:
        gmsh.finalize()

    size_mb = os.path.getsize(out_msh) / 1e6
    print(f"[stl_to_msh] wrote {out_msh} ({size_mb:.1f} MB)")
    return out_msh


if __name__ == "__main__":
    stl = os.environ.get("TESTCASE_STL", DEFAULT_STL)
    msh = os.environ.get("TESTCASE_MSH", DEFAULT_MSH)
    h = float(os.environ.get("TESTCASE_ELEMENT_SIZE", "0.004"))
    order = int(os.environ.get("TESTCASE_ORDER", "1"))
    stl_to_volume_msh(stl, msh, element_size=h, order=order)
