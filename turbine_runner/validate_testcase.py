"""Experimental validation: free-free modal analysis of the test-case disc.

Pipeline: TestCaseGeomertyMesh.stl -> gmsh volume mesh -> RunnerModalSolver with
BCConfig(mode="free") -> discard the 6 rigid-body modes -> compare the elastic
eigenfrequencies with the experimental modal analysis from
``2026.07.15_NatFreqShare4Tobias.docx`` (impact test in air, free suspension).

Runs in the fenicsx container, from turbine_runner/:
    python3 validate_testcase.py
    TESTCASE_ELEMENT_SIZE=0.003 TESTCASE_FORCE_REMESH=1 python3 validate_testcase.py

Defaults are validation-grade: quadratic elements on a tet10 mesh solved with the
SLEPc backend (P1/scipy overestimates bending-dominated modes ~15-20%). Override
with TESTCASE_ELEMENT_DEGREE=1 / TESTCASE_BACKEND=scipy for quick smoke runs.
"""

import json
import os

import numpy as np

from config import MaterialConfig, BCConfig, MeshConfig, SolverConfig, OutputConfig
from mesh_prep import load_and_prepare_mesh
from solver import RunnerModalSolver
from stl_to_msh import stl_to_volume_msh, DEFAULT_STL, DEFAULT_MSH
from main import _write_results

# Reference data from 2026.07.15_NatFreqShare4Tobias.docx (table) and its
# embedded ANSYS report (image). "ND" = nodal-diameter mode of the disc; each ND
# mode is a degenerate sin/cos pair, torsion is a singlet.
EXPERIMENT_HZ = {"1ND": 192.8, "Torsion": None, "2ND": 299.125, "3ND": 712.0, "4ND": 1320.0}
ANSYS_TABLE_HZ = {"1ND": 191.6, "Torsion": 226.0, "2ND": 293.625, "3ND": 703.25, "4ND": 1310.875}
ANSYS_REPORT_HZ = {"1ND": 196.05, "Torsion": 229.11, "2ND": 291.58, "3ND": 694.47, "4ND": 1291.5}

# Degeneracy pattern in ascending frequency order (matches the ANSYS report):
# ND modes come in pairs, torsion is a single mode.
EXPECTED_SEQUENCE = ["1ND", "1ND", "Torsion", "2ND", "2ND", "3ND", "3ND", "4ND", "4ND"]

RIGID_THRESHOLD_HZ = 1.0


def elastic_modes(frequencies, eigenvectors):
    """Drop rigid-body modes (near-zero frequencies) from a free-free solve."""
    keep = [i for i, f in enumerate(frequencies) if f >= RIGID_THRESHOLD_HZ]
    elastic_f = [float(frequencies[i]) for i in keep]
    elastic_v = [eigenvectors[i] for i in keep]
    n_rigid = len(frequencies) - len(keep)
    return n_rigid, elastic_f, elastic_v


def assign_mode_labels(elastic_frequencies):
    """Assign 1ND/Torsion/2ND/... labels by order and degeneracy pattern."""
    labeled = {}
    for freq, label in zip(elastic_frequencies, EXPECTED_SEQUENCE):
        labeled.setdefault(label, []).append(freq)
    return labeled


def run_validation() -> dict:
    """Run the full validation pipeline and return the result summary.

    Returns a dict with all_frequencies_hz, rigid_modes_removed,
    elastic_frequencies_hz, comparison and json_path. Called by main() and by
    test_testcase_validation.py.
    """
    material = MaterialConfig(
        youngs_modulus=75.854e9,
        density=8910.0,
        poisson_ratio=0.34,
    )
    bc_config = BCConfig(mode="free")
    msh_path = os.environ.get("TESTCASE_MSH", DEFAULT_MSH)
    mesh_config = MeshConfig(msh_path=msh_path)
    num_eig = int(os.environ.get("TESTCASE_NUM_EIG", "18"))
    solver_config = SolverConfig(
        num_eigenvalues=num_eig,
        tolerance=float(os.environ.get("TESTCASE_TOL", "1e-8")),
        element_degree=int(os.environ.get("TESTCASE_ELEMENT_DEGREE", "2")),
        solver_backend=os.environ.get("TESTCASE_BACKEND", "slepc"),
    )
    output_config = OutputConfig(output_dir=os.path.join(os.path.dirname(msh_path),
                                                         "..", "output", "testcase"))

    if not os.path.isfile(msh_path) or os.environ.get("TESTCASE_FORCE_REMESH") == "1":
        element_size = float(os.environ.get("TESTCASE_ELEMENT_SIZE", "0.004"))
        stl_to_volume_msh(os.environ.get("TESTCASE_STL", DEFAULT_STL), msh_path,
                          element_size=element_size)

    print("=" * 72)
    print("Test-case validation: free-free modal analysis vs experiment")
    print("=" * 72)
    print(f"Mesh:     {msh_path}")
    print(f"Material: E={material.youngs_modulus:.3e} Pa, "
          f"rho={material.density} kg/m^3, nu={material.poisson_ratio}")
    print("BC:       free-free (rigid modes discarded)")
    print()

    domain = load_and_prepare_mesh(mesh_config)
    solver = RunnerModalSolver(domain, material, bc_config, solver_config)
    eigenvalues, eigenvectors = solver.solve()
    frequencies = solver.compute_frequencies(eigenvalues)

    n_rigid, elastic_f, elastic_v = elastic_modes(frequencies, eigenvectors)
    print()
    print(f"Rigid-body modes removed: {n_rigid} "
          f"(lowest: {', '.join(f'{f:.2e}' for f in frequencies[:n_rigid])} Hz)")
    print(f"Elastic modes ({len(elastic_f)}): "
          f"{', '.join(f'{f:.2f}' for f in elastic_f)}")
    print()

    labeled = assign_mode_labels(elastic_f)
    print(f"{'Mode':<10} {'computed':>10} {'exp.':>10} {'err %':>8} "
          f"{'ANSYS tbl':>10} {'ANSYS rep':>10}")
    print("-" * 64)
    comparison = {}
    for label, ansys_t in ANSYS_TABLE_HZ.items():
        computed = labeled.get(label)
        if not computed:
            continue
        mean_f = float(np.mean(computed))
        exp_f = EXPERIMENT_HZ[label]
        err = (mean_f - exp_f) / exp_f * 100.0 if exp_f else None
        comparison[label] = {
            "computed_hz": computed,
            "computed_mean_hz": mean_f,
            "experiment_hz": exp_f,
            "error_pct": err,
            "ansys_table_hz": ansys_t,
            "ansys_report_hz": ANSYS_REPORT_HZ[label],
        }
        print(f"{label:<10} {mean_f:>10.2f} "
              f"{exp_f if exp_f else float('nan'):>10.3f} "
              f"{err if err is not None else float('nan'):>8.2f} "
              f"{ansys_t:>10.3f} {ANSYS_REPORT_HZ[label]:>10.2f}")
    print()

    os.makedirs(output_config.output_dir, exist_ok=True)
    json_path = os.path.join(output_config.output_dir, "testcase_frequencies.json")
    with open(json_path, "w") as fh:
        json.dump(
            {
                "all_frequencies_hz": [float(f) for f in frequencies],
                "rigid_modes_removed": n_rigid,
                "elastic_frequencies_hz": elastic_f,
                "comparison": comparison,
                "material": {"E_pa": material.youngs_modulus,
                             "rho_kg_m3": material.density,
                             "nu": material.poisson_ratio},
                "bc": "free-free",
                "mesh": msh_path,
            },
            fh, indent=2,
        )
    print(f"Results written to: {json_path}")

    if output_config.save_xdmf:
        _write_results(solver, elastic_f, elastic_v, output_config)

    return {
        "all_frequencies_hz": [float(f) for f in frequencies],
        "rigid_modes_removed": n_rigid,
        "elastic_frequencies_hz": elastic_f,
        "comparison": comparison,
        "json_path": json_path,
    }


def main() -> None:
    run_validation()
    print("=" * 72)
    print("Done")


if __name__ == "__main__":
    main()
