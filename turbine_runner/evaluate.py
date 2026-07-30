"""Headless eigenfrequency evaluation — runs inside the FEniCSx enroot container.

Loads a runner .msh, solves the modal problem, prints one JSON line to stdout.
The host-side runner (adapters/cluster/runner.py) parses that line.

Usage:
    python3 evaluate.py /worker_data/runner.msh

Output (last stdout line):
    RESULT_JSON {"frequencies_hz": [...], "ok": true}

The repo is mounted at /workspace; add src/ to sys.path so the eigenfrequencies
package is importable without a pip install inside the container.
"""

import json
import sys
from pathlib import Path

# Allow import of eigenfrequencies package from the mounted repo.
_src = Path(__file__).parents[1] / "src"
if str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

from eigenfrequencies.config import BCConfig, MaterialConfig, MeshConfig, SolverConfig
from eigenfrequencies.io import load_and_prepare_mesh
from eigenfrequencies.solver import ModalSolver


def evaluate(msh_path: str) -> dict:
    material = MaterialConfig()
    bc = BCConfig()
    mesh_cfg = MeshConfig(msh_path=msh_path)
    solver_cfg = SolverConfig()

    domain = load_and_prepare_mesh(mesh_cfg)
    solver = ModalSolver(domain, material, bc, solver_cfg)
    eigenvalues, _ = solver.solve()
    frequencies = solver.compute_frequencies(eigenvalues)
    return {"frequencies_hz": [float(f) for f in frequencies], "ok": True}


if __name__ == "__main__":
    msh_path = sys.argv[1] if len(sys.argv) > 1 else MeshConfig().msh_path
    try:
        result = evaluate(msh_path)
    except Exception as exc:
        result = {"frequencies_hz": [], "ok": False, "error": f"{type(exc).__name__}: {exc}"}
    print("RESULT_JSON " + json.dumps(result))
