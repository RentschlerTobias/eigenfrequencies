"""Beam configuration parameters for modal analysis."""

import os
from dataclasses import dataclass


@dataclass
class BeamConfig:
    """Configuration for a rectangular beam.

    Attributes:
        length: Beam length in meters
        width: Beam width in meters
        height: Beam height in meters
        youngs_modulus: Young's modulus in Pa
        density: Material density in kg/m³
        mesh_resolution: Target mesh element size
    """
    length: float = 10.0
    width: float = 0.01
    height: float = 0.1
    youngs_modulus: float = 210e9
    density: float = 7850.0
    mesh_resolution: float = 0.05

    @property
    def cross_section_area(self) -> float:
        return self.width * self.height

    @property
    def moment_of_inertia_y(self) -> float:
        return self.width * self.height**3 / 12

    @property
    def moment_of_inertia_z(self) -> float:
        return self.height * self.width**3 / 12


@dataclass
class SolverConfig:
    """Configuration for the modal solver.

    Attributes:
        freq_min: Minimum frequency to search for in Hz
        freq_max: Maximum frequency to search for in Hz
        num_eigenvalues: Number of eigenvalues to compute
        tolerance: Solver tolerance
    """

    freq_min: float = 0.0
    freq_max: float = 1000.0
    num_eigenvalues: int = 10
    tolerance: float = 1e-6


@dataclass
class OutputConfig:
    """Configuration for output options.

    Attributes:
        save_vtk: Save results as VTK files
        save_xdmf: Save results as XDMF files
        output_dir: Output directory for results
    """

    save_vtk: bool = True
    save_xdmf: bool = True
    output_dir: str = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "output")
