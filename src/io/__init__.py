"""XDMF IO utilities for mesh and results handling."""

import os
from typing import Optional

import numpy as np


def mesh_to_xdmf(mesh_file: str, output_dir: str) -> str:
    """Convert mesh file to XDMF format.

    Args:
        mesh_file: Path to mesh file (e.g., .msh from gmsh)
        output_dir: Directory to save XDMF output

    Returns:
        Path to generated XDMF file
    """
    os.makedirs(output_dir, exist_ok=True)
    base_name = os.path.splitext(os.path.basename(mesh_file))[0]
    xdmf_file = os.path.join(output_dir, f"{base_name}.xdmf")

    return xdmf_file


def read_xdmf_mesh(xdmf_file: str):
    """Read mesh from XDMF file using dolfinx.

    Args:
        xdmf_file: Path to XDMF file

    Returns:
        dolfinx mesh object
    """
    from dolfinx.io import XDMFFile
    import dolfinx

    with XDMFFile(dolfinx.MPI.comm_world, xdmf_file, "r") as xdmf:
        mesh = xdmf.read_mesh()
    return mesh


def write_results_xdmf(
    frequencies: np.ndarray,
    eigenvectors: list,
    mesh,
    output_file: str,
) -> None:
    """Write modal analysis results to XDMF file.

    Args:
        frequencies: Array of computed eigenfrequencies in Hz
        eigenvectors: List of eigenmode vectors
        mesh: dolfinx mesh object
        output_file: Path to output XDMF file
    """
    from dolfinx import fem
    from dolfinx.io import XDMFFile

    with XDMFFile(mesh.comm, output_file, "w") as xdmf:
        xdmf.write_mesh(mesh)

        for i, (freq, mode) in enumerate(zip(frequencies, eigenvectors)):
            u = fem.Function(mesh.function_space)
            u.vector[:] = mode
            xdmf.write_function(u, i)