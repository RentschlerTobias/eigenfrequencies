"""Generate the deterministic volume mesh used by the mesh-loading tests.

The suite used to load ``turbine_runner/data/testcase_coarse.msh``, built from
``TestCaseGeomertyMesh.stl``. Both files are matched by ``*.msh``/``*.stl`` in
.gitignore, were never committed, and are gone. Rather than depend on a file
that cannot be restored, the loader tests now run against a mesh this script
produces from scratch.

Regenerate with::

    python tests/fixtures/make_fixture_mesh.py

The output is committed with ``git add -f`` (the repo already tracks a handful
of mesh files that way). Keep it small: it exists to prove the loader handles a
real 3-D volume mesh, not to say anything about physics.
"""

import os

import gmsh

HERE = os.path.dirname(os.path.abspath(__file__))
OUTPUT = os.path.join(HERE, "unit_box_coarse.msh")

# Deliberately coarse — a few hundred tets is plenty to exercise the loader.
ELEMENT_SIZE = 0.25
BOX = (1.0, 0.5, 0.25)  # lx, ly, lz


def generate(path: str = OUTPUT) -> str:
    """Write a coarse tetrahedral box mesh with a physical volume group."""
    gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        # Fixed seed and algorithm so the mesh is byte-stable across machines.
        gmsh.option.setNumber("Mesh.RandomSeed", 1.0)
        gmsh.option.setNumber("Mesh.Algorithm3D", 1)  # Delaunay
        gmsh.model.add("unit_box_coarse")

        vol = gmsh.model.occ.addBox(0.0, 0.0, 0.0, *BOX)
        gmsh.model.occ.synchronize()

        gmsh.option.setNumber("Mesh.CharacteristicLengthMin", ELEMENT_SIZE)
        gmsh.option.setNumber("Mesh.CharacteristicLengthMax", ELEMENT_SIZE)

        # A physical group is mandatory: the dolfinx gmsh reader refuses a mesh
        # without one before any of our own checks get a chance to run.
        gmsh.model.addPhysicalGroup(3, [vol], tag=1)
        gmsh.model.setPhysicalName(3, 1, "volume")

        gmsh.model.mesh.generate(3)
        gmsh.write(path)
    finally:
        gmsh.finalize()
    return path


if __name__ == "__main__":
    out = generate()
    print(f"wrote {out}")
