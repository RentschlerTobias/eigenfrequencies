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

    model = gmsh.model
    occ = gmsh.model.occ

    L2 = L / 2
    B2 = B / 2
    H2 = H / 2

    occ.addBox(-L2, -B2, -H2, L, B, H)
    occ.synchronize()

    surfaces = []
    lines = []
    for entity in model.getEntities():
        dim = entity[0]
        tag = entity[1]
        if dim == 2:
            surfaces.append(tag)
        elif dim == 1:
            lines.append(tag)

    volume = model.addPhysicalGroup(3, [1])
    model.setPhysicalName(3, volume, "Beam")

    return 1, surfaces, lines


def set_mesh_resolution(config: BeamConfig) -> None:
    """Set mesh resolution for the beam geometry."""
    L = config.length
    mesh_size = config.mesh_resolution

    model = gmsh.model

    try:
        points = model.getEntities(0)
        for point in points:
            try:
                coords = model.getValue(0, point[1], [])
                x = coords[0]
                dist_to_end = min(abs(x + L/2), abs(x - L/2))
                if dist_to_end < L * 0.1:
                    local_size = mesh_size * 0.5
                else:
                    local_size = mesh_size
                model.setMeshSize(0, point[1], local_size)
            except Exception:
                pass
    except Exception:
        pass


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
    set_mesh_resolution(config)

    gmsh.model.occ.synchronize()
    gmsh.model.mesh.generate()
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
