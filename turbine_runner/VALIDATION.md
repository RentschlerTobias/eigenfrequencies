# Validation: free-free modal analysis vs experiment

Date: 2026-07-20 · Status: **PASSED** (all measured modes within 5%)

The `turbine_runner` modal pipeline is validated against an experimental modal
analysis of a bronze test disc (`../TestCaseGeomertyMesh.stl`, exported from
ANSYS Mechanical). Reference data: `2026.07.15_NatFreqShare4Tobias.docx`
(impact test in air, free suspension) with its embedded ANSYS report.

## Setup

| | |
|---|---|
| Material | bronze: E = 75.854 GPa, rho = 8910 kg/m3, nu = 0.34 |
| Boundary condition | free-free (matches experiment; 6 rigid-body modes discarded) |
| Geometry | STL, 206,472 triangles, watertight; disc d = 0.2 m, h = 87 mm; mass ~5.99 kg |
| Mesh | `data/testcase_volume.msh`: 325,067 tet10, 654,958 P2 nodes -> 1,964,874 vector DOFs (`TESTCASE_ELEMENT_SIZE=0.006`, order 2) |
| Solver | SLEPc GHEP, shift-invert sigma = -1 (K + M is SPD), KSP preonly + LU/MUMPS; Rayleigh-quotient refinement of eigenvalues |
| Container | `eigenfrequencies-fenicsx:latest` (dolfinx 0.11, slepc4py 3.25.1) |
| Resources | wall ~3-5 min, peak RAM 28.6 GB (30 GB host) |

Why P2 + SLEPc: linear tet4 elements over-stiffen the bending-dominated
nodal-diameter (ND) modes. With identical material/geometry the P1 discretization
(357,671 tets, 353k DOFs, scipy backend) landed +14-20% above experiment, while
ANSYS (quadratic elements) matches — so discretization was the only lever.
Quadratic tets fix the physics but push the problem to ~2M DOFs, beyond scipy's
dense factorization; hence the SLEPc shift-invert backend with MUMPS.

## Results (P2, tet10)

6 rigid-body modes removed (3.5e-04 ... 9.1e-04 Hz). 12 elastic modes:
192.39, 192.51, 223.73, 290.12, 290.20, 693.92, 693.93, 1291.48, 1291.52,
1368.12, 1368.70, 1518.29 Hz.

| Mode | Computed pair (Hz) | Mean (Hz) | Experiment (Hz) | Error | ANSYS table | ANSYS report |
|------|--------------------|-----------|-----------------|-------|-------------|--------------|
| 1ND     | 192.39 / 192.51   | 192.45  | 192.8   | **-0.18%** | 191.6    | 196.05  |
| Torsion | 223.73 (singlet)  | 223.73  | not measured | — | 226.0    | 229.11  |
| 2ND     | 290.12 / 290.20   | 290.16  | 299.125 | **-3.00%** | 293.625  | 291.58  |
| 3ND     | 693.92 / 693.93   | 693.92  | 712.0   | **-2.54%** | 703.25   | 694.47  |
| 4ND     | 1291.48 / 1291.52 | 1291.50 | 1320.0  | **-2.16%** | 1310.875 | 1291.50 |

ND modes are degenerate sin/cos pairs (rotational symmetry); torsion is a
singlet. Pair splitting < 0.1 Hz confirms the mesh preserves the symmetry.

### Higher modes (cross-check against the ANSYS report, no experiment)

| Computed (Hz) | ANSYS report mode | ANSYS (Hz) | Deviation |
|---------------|-------------------|------------|-----------|
| 1368.12 / 1368.70 | Couronne_2ND | 1371.2 / 1371.6 | -0.22% |
| 1518.29 | CompressionAxiale | 1521.1 | -0.18% |

## P1 vs P2 (same geometry, same material)

| Mode | P1 tet4 (Hz) | P1 error | P2 tet10 (Hz) | P2 error |
|------|--------------|----------|---------------|----------|
| 1ND | 231.26 | +19.95% | 192.45 | -0.18% |
| Torsion | 266.90 | +18.10%* | 223.73 | -0.99%* |
| 2ND | 356.43 | +19.16% | 290.16 | -3.00% |
| 3ND | 854.82 | +20.06% | 693.92 | -2.54% |
| 4ND | 1510.50 | +14.43% | 1291.50 | -2.16% |

\* torsion was not measured; compared against ANSYS table value 226.0 Hz.

The systematic positive P1 bias is the classic tet4 bending over-stiffness:
ND modes are rod/crown bending with only 2-4 linear elements across the thin
features. P2 removes it; the small remaining negative bias (-2 to -3%) is
consistent with a converging-from-above discretization plus modest mass
idealization differences vs the physical part.

## Reproduce

```bash
# mesh once (skip if data/testcase_volume.msh exists)
docker run --rm -i -e PYTHONUNBUFFERED=1 \
  -e TESTCASE_ORDER=2 -e TESTCASE_ELEMENT_SIZE=0.006 \
  -v "$PWD:/workspace" -w /workspace/turbine_runner \
  eigenfrequencies-fenicsx:latest python3 stl_to_msh.py

# full validation run
docker run --rm -i -e PYTHONUNBUFFERED=1 \
  -v "$PWD:/workspace" -w /workspace/turbine_runner \
  eigenfrequencies-fenicsx:latest python3 validate_testcase.py
```

Env overrides: `TESTCASE_STL`, `TESTCASE_MSH`, `TESTCASE_ELEMENT_SIZE`,
`TESTCASE_ORDER`, `TESTCASE_FORCE_REMESH=1`, `TESTCASE_NUM_EIG`,
`TESTCASE_TOL`, `TESTCASE_ELEMENT_DEGREE`, `TESTCASE_BACKEND`.

## Repo test

`test_testcase_validation.py` runs the full pipeline and asserts 6 rigid
modes, >= 9 elastic modes and every measured mode within 5%. Heavyweight
(~5 min, ~29 GB RAM), therefore opt-in:

```bash
docker run --rm -i -e PYTHONUNBUFFERED=1 -e RUN_TESTCASE_VALIDATION=1 \
  -v "$PWD:/workspace" -w /workspace/turbine_runner \
  eigenfrequencies-fenicsx:latest \
  python3 -m pytest test_testcase_validation.py -v
```

Unit tests of the solver backends (fast, dense-reference block):
`python3 -m pytest test_free_mode.py`.

## Artifacts

- `output/testcase/testcase_frequencies.json` — all frequencies + comparison dict
- `output/testcase/modes.xdmf` / `modes.h5` — 12 elastic mode shapes (ParaView)
- `output/testcase/modes.pvd`, `geometry.pvd`

## Limitations

- Torsion mode unmeasured experimentally; validated only against ANSYS (both
  predictions within ~1-2% of our 223.73 Hz).
- Mode labels are assigned positionally (expected degeneracy sequence); a
  different geometry would need mode-shape inspection.
- Peak RAM 28.6 GB leaves little headroom on a 30 GB host; the CG+GAMG
  fallback (slower) engages automatically if MUMPS factorization fails.
