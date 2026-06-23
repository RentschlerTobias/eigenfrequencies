"""Spline beam geometry generation using gmsh."""

import os
from typing import Tuple, List

import numpy as np
import gmsh
from scipy.interpolate import make_interp_spline

from config import BeamConfig, SplineConfig


def create_spline_beam(
    beam_config: BeamConfig,
    spline_config: SplineConfig,
) -> Tuple[int, List[int], List[int]]:
    """Create a spline beam geometry with B-spline spine.
    
    The beam follows a 3-point B-spline curve:
    P0 = (0, 0, 0) - fixed
    P1 = (x1, y1, 0) - middle control point
    P2 = (L, y2, 0) - end point
    
    Cross-sections are created at N points along the spline and
    lofted together to form a solid volume.
    
    Args:
        beam_config: Beam configuration (L, B, H, material)
        spline_config: Spline control points and number of sections
        
    Returns:
        Tuple of (volume_tag, surface_tags, line_tags)
    """
    L, B, H = beam_config.length, beam_config.width, beam_config.height
    lc = beam_config.mesh_resolution
    x1, y1, y2 = spline_config.x1, spline_config.y1, spline_config.y2
    N = spline_config.num_sections
    
    # Control points for B-spline (all 3 points)
    ctrl_pts = np.array([
        [0.0, 0.0, 0.0],
        [x1, y1, 0.0],
        [L, y2, 0.0],
    ])
    
    # Evaluate N points along the spline (parameter t from 0 to 1)
    t = np.linspace(0, 1, N)
    # Create a simple B-spline interpolation (k=2 for quadratic)
    t_knots = np.linspace(0, 1, len(ctrl_pts))
    spl = make_interp_spline(t_knots, ctrl_pts, k=2)
    spine_points = spl(t)
    
    occ = gmsh.model.occ
    model = gmsh.model
    
    # Create cross-sections at each spine point
    # Each cross-section is a rectangle in the y-z plane
    wires = []
    
    for i, (x, y, z) in enumerate(spine_points):
        B2 = B / 2
        H2 = H / 2
        
        # Create 4 points for the rectangular cross-section
        p1 = occ.addPoint(x, y - B2, z - H2, lc)
        p2 = occ.addPoint(x, y + B2, z - H2, lc)
        p3 = occ.addPoint(x, y + B2, z + H2, lc)
        p4 = occ.addPoint(x, y - B2, z + H2, lc)
        
        # Create lines forming the cross-section
        l1 = occ.addLine(p1, p2)
        l2 = occ.addLine(p2, p3)
        l3 = occ.addLine(p3, p4)
        l4 = occ.addLine(p4, p1)
        
        # Create a wire (curve loop) for the cross-section
        wire = occ.addCurveLoop([l1, l2, l3, l4])
        wires.append(wire)
    
    # Create the lofted solid from all cross-sections
    # addThruSections creates a solid volume through all cross-sections
    vols = occ.addThruSections(wires, makeSolid=True, makeRuled=False)
    
    # Get the volume tag (first volume)
    volume_tag = vols[0][1]
    
    # Synchronize to get all entities
    occ.synchronize()
    
    # Get all surfaces
    surfaces = [tag for dim, tag in model.getEntities(2)]
    # Get all lines
    lines = [tag for dim, tag in model.getEntities(1)]
    
    # Add physical groups
    model.addPhysicalGroup(3, [volume_tag])
    model.setPhysicalName(3, volume_tag, "Beam")
    
    return volume_tag, surfaces, lines


def generate_spline_mesh(
    beam_config: BeamConfig,
    spline_config: SplineConfig,
    output_path: str,
) -> str:
    """Generate spline beam mesh and save to .msh format.
    
    Args:
        beam_config: Beam configuration
        spline_config: Spline configuration
        output_path: Directory to save mesh files
        
    Returns:
        Path to the generated .msh file
    """
    gmsh.initialize()
    gmsh.option.setNumber("Mesh.Algorithm", 6)
    
    model = gmsh.model
    model.add("spline_beam")
    
    create_spline_beam(beam_config, spline_config)
    
    gmsh.model.occ.synchronize()
    gmsh.model.mesh.generate(3)
    gmsh.write(os.path.join(output_path, "beam.msh"))
    
    gmsh.finalize()
    
    return os.path.join(output_path, "beam.msh")


def spline_beam_to_xdmf(
    beam_config: BeamConfig,
    spline_config: SplineConfig,
    output_dir: str,
) -> str:
    """Convert spline beam mesh to XDMF format.
    
    Args:
        beam_config: Beam configuration
        spline_config: Spline configuration
        output_dir: Directory for output files
        
    Returns:
        Path to the generated file
    """
    os.makedirs(output_dir, exist_ok=True)
    
    msh_file = generate_spline_mesh(beam_config, spline_config, output_dir)
    
    return msh_file
