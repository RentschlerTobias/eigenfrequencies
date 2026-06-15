"""Headless frequency evaluation for the optimizer (runs in the fenicsx container).

Loads a runner .msh, solves the modal problem, prints the eigenfrequencies as a
single JSON line to stdout (no XDMF/VTK). The host optimizer parses that line.

Usage:
    python3 evaluate.py /work/runner.msh
Output (stdout, last line):
    {"frequencies_hz": [...], "ok": true}
"""

import json
import sys

from config import MaterialConfig, BCConfig, MeshConfig, SolverConfig
from mesh_prep import load_and_prepare_mesh
from solver import RunnerModalSolver


def evaluate(msh_path: str) -> dict:
    material = MaterialConfig()
    bc_config = BCConfig()
    mesh_config = MeshConfig(msh_path=msh_path)
    solver_config = SolverConfig()

    domain = load_and_prepare_mesh(mesh_config)
    solver = RunnerModalSolver(domain, material, bc_config, solver_config)
    eigenvalues, _ = solver.solve()
    frequencies = solver.compute_frequencies(eigenvalues)
    return {"frequencies_hz": [float(f) for f in frequencies], "ok": True}


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else MeshConfig().msh_path
    try:
        result = evaluate(path)
    except Exception as exc:  # noqa: BLE001 - report failure to the optimizer
        result = {"frequencies_hz": [], "ok": False, "error": f"{type(exc).__name__}: {exc}"}
    # Machine-readable result on the final stdout line.
    print("RESULT_JSON " + json.dumps(result))
