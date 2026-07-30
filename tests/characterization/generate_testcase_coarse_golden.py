"""Generate golden reference for Laval disc coarse modal solver.

Runs inside the fenicsx container.
"""
import json
import hashlib
import os
import sys
import subprocess

import numpy as np
from eigenfrequencies.config import BCConfig, MaterialConfig, MeshConfig, SolverConfig
from eigenfrequencies.io import load_and_prepare_mesh
from eigenfrequencies.solver import ModalSolver

from eigenfrequencies.io import DEFAULT_MSH, DEFAULT_STL, stl_to_volume_msh


def compute_mesh_hash(mesh_file: str) -> str:
    h = hashlib.sha256()
    with open(mesh_file, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def extract_mode_shape_norms(eigenvectors, domain):
    """Return displacement-norm vector per mode for MAC computation.

    For free-free solves, the eigenvectors include rigid-body modes.
    We keep all modes (including rigid) in the golden so the test can
    compare the same number of modes, but we also record which are elastic.
    """
    V = domain.function_space if hasattr(domain, 'function_space') else None
    # Get node coordinates from the domain geometry
    coords = domain.geometry.x
    num_nodes = coords.shape[0]

    norms = []
    for ev in eigenvectors:
        # ev is a flat array of DOFs; for P1 vector space it's 3*num_nodes
        if len(ev) >= num_nodes * 3:
            u = ev[:num_nodes * 3].reshape((num_nodes, 3))
        else:
            # For higher order, just take what we can
            u = ev.reshape((-1, 3))
        disp_norm = np.linalg.norm(u, axis=1)
        norms.append(disp_norm.tolist())
    return norms


def main():
    # Coarse mesh settings
    element_size = 0.01  # coarse element size (vs 0.004 validation grade)
    element_degree = 1     # P1 linear elements (vs P2 validation grade)
    solver_backend = "scipy"
    num_eigenvalues = 16  # ask for 16 to get 10 elastic after removing rigid modes

    material = MaterialConfig(
        youngs_modulus=75.854e9,
        density=8910.0,
        poisson_ratio=0.34,
    )
    bc_config = BCConfig(mode="free")

    # Use a dedicated coarse mesh path
    _REPO_ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
    msh_path = os.path.join(_REPO_ROOT, "turbine_runner", "data", "testcase_coarse.msh")
    mesh_config = MeshConfig(msh_path=msh_path)
    solver_config = SolverConfig(
        num_eigenvalues=num_eigenvalues,
        tolerance=1e-6,
        element_degree=element_degree,
        solver_backend=solver_backend,
    )

    out_dir = os.path.dirname(os.path.abspath(__file__))
    os.makedirs(out_dir, exist_ok=True)

    # Generate coarse mesh if missing
    stl_path = DEFAULT_STL
    if not os.path.isfile(msh_path):
        print(f"[generate_testcase_coarse] generating coarse mesh: element_size={element_size}, order={element_degree}")
        stl_to_volume_msh(stl_path, msh_path, element_size=element_size, order=element_degree)
    else:
        print(f"[generate_testcase_coarse] reusing existing mesh: {msh_path}")

    mesh_hash = compute_mesh_hash(msh_path)

    # Solve
    domain = load_and_prepare_mesh(mesh_config)
    solver = ModalSolver(domain, material, bc_config, solver_config)
    eigenvalues, eigenvectors = solver.solve()
    frequencies = solver.compute_frequencies(eigenvalues)

    # For free-free, remove rigid-body modes (freq < 1 Hz threshold)
    rigid_threshold_hz = 1.0
    keep = [i for i, f in enumerate(frequencies) if f >= rigid_threshold_hz]
    n_rigid = len(frequencies) - len(keep)
    elastic_frequencies = [float(frequencies[i]) for i in keep]
    elastic_eigenvectors = [eigenvectors[i] for i in keep]

    print(f"[generate_testcase_coarse] rigid modes removed: {n_rigid}")
    print(f"[generate_testcase_coarse] elastic frequencies: {elastic_frequencies}")

    # Take first 10 elastic modes
    first_10_freqs = elastic_frequencies[:10]
    first_10_vectors = elastic_eigenvectors[:10]

    # Extract mode-shape displacement norms
    mode_shapes = extract_mode_shape_norms(first_10_vectors, domain)

    # Get git SHA
    repo_dir = os.path.join(os.path.dirname(__file__), "..", "..")
    try:
        subprocess.run(["git", "config", "--global", "--add", "safe.directory", repo_dir],
                       check=False, capture_output=True)
        git_sha = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=repo_dir
        ).decode().strip()
    except subprocess.CalledProcessError:
        git_sha = "unknown"

    golden = {
        "frequencies": first_10_freqs,
        "mode_shapes": mode_shapes,
        "solver_settings": {
            "boundary_type": "free",
            "element_degree": element_degree,
            "tolerance": solver_config.tolerance,
            "num_eigenvalues": num_eigenvalues,
            "solver_backend": solver_backend,
            "rigid_modes_removed": n_rigid,
            "rigid_threshold_hz": rigid_threshold_hz,
        },
        "mesh_hash": mesh_hash,
        "git_sha": git_sha,
        "source_config": {
            "material": {
                "youngs_modulus": material.youngs_modulus,
                "density": material.density,
                "poisson_ratio": material.poisson_ratio,
            },
            "mesh": {
                "stl_path": stl_path,
                "msh_path": msh_path,
                "element_size": element_size,
                "order": element_degree,
            },
            "solver": {
                "num_eigenvalues": num_eigenvalues,
                "tolerance": solver_config.tolerance,
                "element_degree": element_degree,
                "solver_backend": solver_backend,
            },
            "bc": {
                "mode": "free",
            },
        },
    }

    out_path = os.path.join(out_dir, "testcase_coarse.json")
    with open(out_path, "w") as f:
        json.dump(golden, f, indent=2)
    print(f"Testcase coarse golden reference written to: {out_path}")


if __name__ == "__main__":
    main()
