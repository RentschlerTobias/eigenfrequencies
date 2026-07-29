"""Generate golden reference for beam modal solver.

Runs inside the fenicsx container.
"""
import json
import hashlib
import os
import subprocess
import tempfile

import numpy as np
from eigenfrequencies.config import BCConfig, MaterialConfig, SolverConfig
from eigenfrequencies.solver import ModalSolver


def _generate_beam_msh(output_dir: str, length=1.0, width=0.1, height=0.01, lc=0.1) -> str:
    """Generate a rectangular beam mesh with gmsh (inline, no demo/beam import)."""
    import gmsh

    gmsh.initialize()
    gmsh.option.setNumber("Mesh.Algorithm", 6)
    gmsh.model.add("beam")

    L, B, H = length, width, height
    B2 = B / 2
    H2 = H / 2

    occ = gmsh.model.occ
    p1 = occ.addPoint(0, -B2, -H2, lc)
    p2 = occ.addPoint(L, -B2, -H2, lc)
    p3 = occ.addPoint(L, B2, -H2, lc)
    p4 = occ.addPoint(0, B2, -H2, lc)
    p5 = occ.addPoint(0, -B2, H2, lc)
    p6 = occ.addPoint(L, -B2, H2, lc)
    p7 = occ.addPoint(L, B2, H2, lc)
    p8 = occ.addPoint(0, B2, H2, lc)

    e1 = occ.addLine(p1, p2)
    e2 = occ.addLine(p2, p3)
    e3 = occ.addLine(p3, p4)
    e4 = occ.addLine(p4, p1)
    e5 = occ.addLine(p5, p6)
    e6 = occ.addLine(p6, p7)
    e7 = occ.addLine(p7, p8)
    e8 = occ.addLine(p8, p5)
    e9 = occ.addLine(p1, p5)
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
    surface_loop = occ.addSurfaceLoop(surfaces)
    volume_tag = occ.addVolume([surface_loop])
    occ.synchronize()

    gmsh.model.addPhysicalGroup(3, [volume_tag])
    gmsh.model.setPhysicalName(3, volume_tag, "Beam")
    gmsh.model.occ.synchronize()
    gmsh.model.mesh.generate(3)

    msh_path = os.path.join(output_dir, "beam.msh")
    gmsh.write(msh_path)
    gmsh.finalize()
    return msh_path


def compute_mesh_hash(mesh_file: str) -> str:
    h = hashlib.sha256()
    with open(mesh_file, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def extract_mode_shape_norms(eigenvectors, mesh_coords):
    """Return displacement-norm vector per mode for MAC computation."""
    num_nodes = len(mesh_coords)
    norms = []
    for ev in eigenvectors:
        if len(ev) >= num_nodes * 3:
            u = ev[:num_nodes * 3].reshape((num_nodes, 3))
        else:
            u = ev.reshape((-1, 3))
        # L2 norm of displacement at each node
        disp_norm = np.linalg.norm(u, axis=1)
        norms.append(disp_norm.tolist())
    return norms


def main():
    output_dir = tempfile.mkdtemp(prefix="beam_golden_")
    mesh_file = _generate_beam_msh(
        output_dir,
        length=1.0,
        width=0.1,
        height=0.01,
        lc=0.1,
    )
    mesh_hash = compute_mesh_hash(mesh_file)

    from dolfinx.io import gmsh
    from mpi4py import MPI

    mesh_data = gmsh.read_from_msh(mesh_file, MPI.COMM_WORLD, rank=0, gdim=3)
    domain = mesh_data.mesh

    material = MaterialConfig(
        youngs_modulus=210e9,
        density=7850.0,
        poisson_ratio=0.0,
    )
    bc_config = BCConfig(
        mode="axial_plane",
        axis="x",
        plane_value=0.0,
        plane_tol=1e-6,
    )
    solver_config = SolverConfig(
        num_eigenvalues=10,
        tolerance=1e-6,
        element_degree=2,
        solver_backend="scipy",
    )

    solver = ModalSolver(domain, material, bc_config, solver_config)
    eigenvalues, eigenvectors = solver.solve()
    frequencies = solver.compute_frequencies(eigenvalues)

    mesh_coords = domain.geometry.x

    # Extract mode-shape displacement norms
    mode_shapes = extract_mode_shape_norms(eigenvectors, mesh_coords)

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
        "frequencies": [float(f) for f in frequencies],
        "mode_shapes": mode_shapes,
        "solver_settings": {
            "boundary_type": "cantilever",
            "element_degree": 2,
            "tolerance": solver_config.tolerance,
            "num_eigenvalues": solver_config.num_eigenvalues,
            "solver_backend": "scipy",
        },
        "mesh_hash": mesh_hash,
        "git_sha": git_sha,
        "source_config": {
            "beam": {
                "length": 1.0,
                "width": 0.1,
                "height": 0.01,
                "youngs_modulus": material.youngs_modulus,
                "density": material.density,
                "mesh_resolution": 0.1,
            },
            "solver": {
                "num_eigenvalues": solver_config.num_eigenvalues,
                "tolerance": solver_config.tolerance,
                "element_degree": solver_config.element_degree,
                "solver_backend": "scipy",
            },
        },
    }

    out_dir = os.path.dirname(os.path.abspath(__file__))
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, "beam.json")
    with open(out_path, "w") as f:
        json.dump(golden, f, indent=2)
    print(f"Beam golden reference written to: {out_path}")


if __name__ == "__main__":
    main()
