"""Result writers: XDMF, VTK, JSON, and headless JSON-line mode.

Ported from ``turbine_runner/main.py`` (full writers) and
``turbine_runner/evaluate.py`` (headless JSON-line mode).
"""

import json
import os
import sys
from typing import Optional


def write_results_json(
    frequencies,
    eigenvalues=None,
    output_path: str = "output/frequencies.json",
) -> None:
    """Write frequencies (and optional eigenvalues) to a JSON file.

    Args:
        frequencies: List of eigenfrequencies in Hz.
        eigenvalues: Optional list of raw eigenvalues.
        output_path: Destination file path.
    """
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    payload = {"frequencies_hz": [float(f) for f in frequencies]}
    if eigenvalues is not None:
        payload["eigenvalues"] = [float(ev) for ev in eigenvalues]
    with open(output_path, "w") as fh:
        json.dump(payload, fh, indent=2)


def write_results_xdmf_vtk(solver, frequencies, eigenvectors, output_config) -> None:
    """Write mesh + mode shapes to XDMF and VTK for ParaView inspection.

    Both formats need the output Function degree to match the mesh geometry
    degree. The dtOO mesh is second-order (tet10) while displacement is solved
    on a lower degree, so each mode is interpolated onto a matching-degree space.

    Args:
        solver: A modal solver instance with ``domain`` and ``V`` attributes.
        frequencies: List of eigenfrequencies in Hz.
        eigenvectors: List of eigenvector arrays.
        output_config: ``OutputConfig`` dataclass with ``output_dir``.
    """
    from dolfinx import fem
    from dolfinx.io import VTKFile, XDMFFile

    geom_degree = solver.domain.geometry.cmap.degree
    V_out = fem.functionspace(solver.domain, ("Lagrange", geom_degree, (3,)))

    # Pre-build the matching-degree mode functions once, reuse for both writers.
    modes = []
    for i, (freq, vec) in enumerate(zip(frequencies, eigenvectors)):
        u = fem.Function(solver.V)
        u.x.array[:] = vec
        u_out = fem.Function(V_out)
        u_out.interpolate(u)
        u_out.name = f"mode_{i + 1}_{freq:.1f}Hz"
        modes.append(u_out)

    xdmf_path = os.path.join(output_config.output_dir, "modes.xdmf")
    with XDMFFile(solver.domain.comm, xdmf_path, "w") as xdmf:
        xdmf.write_mesh(solver.domain)
        for i, u_out in enumerate(modes):
            xdmf.write_function(u_out, float(i))
    print(f"Mode shapes written to: {xdmf_path}")

    # VTK: geometry-only file (for quick shape inspection) + mode-shape series.
    geom_pvd = os.path.join(output_config.output_dir, "geometry.pvd")
    with VTKFile(solver.domain.comm, geom_pvd, "w") as vtk:
        vtk.write_mesh(solver.domain)
    print(f"Geometry written to: {geom_pvd}")

    modes_pvd = os.path.join(output_config.output_dir, "modes.pvd")
    with VTKFile(solver.domain.comm, modes_pvd, "w") as vtk:
        for i, u_out in enumerate(modes):
            vtk.write_function(u_out, float(i))
    print(f"Mode shapes (VTK) written to: {modes_pvd}")
    print(f"Mode shapes written to: {xdmf_path}")


def write_result_line(
    frequencies,
    eigenvalues=None,
    ok: bool = True,
    file=None,
) -> bytes:
    """Headless JSON-line mode: serialize frequencies as a compact JSON line.

    Mirrors the machine-readable output of ``turbine_runner/evaluate.py``.

    Args:
        frequencies: List of eigenfrequencies in Hz.
        eigenvalues: Optional list of raw eigenvalues.
        ok: Boolean success flag.
        file: Optional file-like object to write the line into.

    Returns:
        The encoded JSON line as UTF-8 bytes (including the trailing ``\\n``).
    """
    result = {"frequencies_hz": [float(f) for f in frequencies], "ok": ok}
    if eigenvalues is not None:
        result["eigenvalues"] = [float(ev) for ev in eigenvalues]
    line = json.dumps(result, separators=(",", ":"))
    encoded = (line + "\n").encode("utf-8")
    if file is not None:
        file.write(encoded)
    return encoded
