"""Eigenfrequencies I/O package — public API."""

from eigenfrequencies.io.axis import inspect_mesh
from eigenfrequencies.io.cfd_eval import evaluate_cfd
from eigenfrequencies.io.load import MeshVerificationError, load_and_prepare_mesh
from eigenfrequencies.io.results import (
    write_result_line,
    write_results_json,
    write_results_xdmf_vtk,
)
from eigenfrequencies.io.stl_to_msh import DEFAULT_MSH, DEFAULT_STL, stl_to_volume_msh

__all__ = [
    "DEFAULT_MSH",
    "DEFAULT_STL",
    "evaluate_cfd",
    "inspect_mesh",
    "load_and_prepare_mesh",
    "MeshVerificationError",
    "stl_to_volume_msh",
    "write_result_line",
    "write_results_json",
    "write_results_xdmf_vtk",
]
