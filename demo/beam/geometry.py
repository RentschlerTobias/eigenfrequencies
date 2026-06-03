"""Beam geometry generation using gmsh."""

import os
from typing import Tuple

import gmsh

from config import BeamConfig


def create_rectangular_beam(config: BeamConfig) -> Tuple[int, int, int]:
    """Create a rectangular beam geometry.

    Args:
        config: Beam configuration with length, width, height

    Returns:
        Tuple of (volume_tag, surface_tags, line_tags)
    """
    L, B, H = config.length, config.width, config.height
    lc = config.mesh_resolution
    model = gmsh.model
    occ = gmsh.model.occ

    L2 = L / 2
    B2 = B / 2
    H2 = H / 2

    p1 = occ.addPoint(-L2, -B2, -H2, lc)
    p2 = occ.addPoint( L2, -B2, -H2, lc)
    p3 = occ.addPoint( L2,  B2, -H2, lc)
    p4 = occ.addPoint(-L2,  B2, -H2, lc)
    p5 = occ.addPoint(-L2, -B2,  H2, lc)
    p6 = occ.addPoint( L2, -B2,  H2, lc)
    p7 = occ.addPoint( L2,  B2,  H2, lc)
    p8 = occ.addPoint(-L2,  B2,  H2, lc)

    e1  = occ.addLine(p1, p2)
    e2  = occ.addLine(p2, p3)
    e3  = occ.addLine(p3, p4)
    e4  = occ.addLine(p4, p1)
    e5  = occ.addLine(p5, p6)
    e6  = occ.addLine(p6, p7)
    e7  = occ.addLine(p7, p8)
    e8  = occ.addLine(p8, p5)
    e9  = occ.addLine(p1, p5)
    e10 = occ.addLine(p2, p6)
    e11 = occ.addLine(p3, p7)
    e12 = occ.addLine(p4, p8)

    bottom_loop = occ.addCurveLoop([e1, e2, e3, e4])
    bottom = occ.addSurfaceFilling(bottom_loop)
    top_loop = occ.addCurveLoop([e5, e6, e7, e8])
    top = occ.addSurfaceFilling(top_loop)
    front_loop = occ.addCurveLoop([e1, e10, e5, e9])
    front = occ.addSurfaceFilling(front_loop)
    back_loop = occ.addCurveLoop([e3, e11, e7, e12])
    back = occ.addSurfaceFilling(back_loop)
    left_loop = occ.addCurveLoop([e4, e12, e8, e9])
    left = occ.addSurfaceFilling(left_loop)
    right_loop = occ.addCurveLoop([e2, e10, e6, e11])
    right = occ.addSurfaceFilling(right_loop)

    surfaces = [bottom, top, front, back, left, right]
    lines = [e1, e2, e3, e4, e5, e6, e7, e8, e9, e10, e11, e12]

    surface_loop = occ.addSurfaceLoop(surfaces)
    volume_tag = occ.addVolume([surface_loop])

    occ.synchronize()

    model.addPhysicalGroup(3, [volume_tag])
    model.setPhysicalName(3, volume_tag, "Beam")

    return 1, surfaces, lines


def generate_mesh(config: BeamConfig, output_path: str) -> str:
    """Generate beam mesh and save to XDMF format.

    Args:
        config: Beam configuration
        output_path: Directory to save mesh files

    Returns:
        Path to the generated XDMF file
    """
    gmsh.initialize()
    gmsh.option.setNumber("Mesh.Algorithm", 6)

    model = gmsh.model
    model.add("beam")

    create_rectangular_beam(config)

    gmsh.model.occ.synchronize()
    gmsh.model.mesh.generate(3)
    gmsh.write(os.path.join(output_path, "beam.msh"))

    gmsh.finalize()

    return os.path.join(output_path, "beam.msh")


def beam_to_xdmf(config: BeamConfig, output_dir: str) -> str:
    """Convert gmsh mesh to XDMF format for FEniCSx.

    Args:
        config: Beam configuration
        output_dir: Directory for output files

    Returns:
        Path to XDMF file (currently just returns .msh path)
    """
    os.makedirs(output_dir, exist_ok=True)

    msh_file = generate_mesh(config, output_dir)

    xdmf_file = os.path.join(output_dir, "beam.xdmf")

    return msh_file
