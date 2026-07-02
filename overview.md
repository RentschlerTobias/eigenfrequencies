Goal
- Extend dtOO-driven Francis-runner **shape optimization** (hydraulic objectives: efficiency, cavitation, design head) with a **structural eigenfrequency penalty** to avoid resonance. Long-term: fluid-structure interaction (FSI). Near-term: dry eigenfrequencies + static-pressure wet added-mass via placeholder ratios.

Constraints & Preferences
- Eigenfrequency objective = **penalty**, not separate Pareto axis (decision a). Keeps hydraulic objective space low-dimensional.
- **Dry modes now**, wet added-mass later (decision b). Dry solve validated; Laplace added-mass is next physical correction.
- Fixed Hz forbidden band [100, 150] Hz now, kinematic blade-passing `Z_guidevanes · n` later.
- Build in **eigenfrequencies** repo; de_framework is reference only (reuse patterns/CFD math, do not fork).
- Sparse BC restriction: free-DOF slice of CSR matrices (no `toarray()`), scales to ~1M P2 DOFs.
- P1 (`element_degree=1`) default for memory safety; P2 deferred to cluster nodes.

Progress
Done
- `config.py`: Material, BC, Mesh, Solver, CFD, Objective, WetMode dataclasses.
- `solver.py`: `RunnerModalSolver` with sparse free-DOF restriction, config-driven hub clamp, rigid-body check.
- `dtoo_export.py`: dtOO → `runner.msh`, parametric via `data/design.json`, cluster-adapted (native, no Docker).
- `evaluate.py`: Headless frequency evaluation (JSON line for optimizer).
- `main.py`: Full report + XDMF/VTK/JSON.
- `optimization.py`: Resonance penalty (`compute_penalty`, `band_report`).
- `optimize.py`: Legacy resonance-only host (dtOO + FEniCSx per eval).
- `optimize_multi.py`: Multi-objective host, CFD optional, degrades to resonance-only.
- `objective.py`: `cfd_scalar` (tanh scalarization) + `resonance_term` → `combined_objective`.
- `cfd_eval.py`: Plain OpenFOAM `postProcessing` reader (no pyDtOO/dolfinx dependency).
- `added_mass.py`: Wet-mode interface + placeholder ratios + `rayleigh_ratios` NotImplementedError stub.
- `mesh_prep.py`: Load + verify volume mesh + axis-discovery diagnostic.
- `cluster/submit.sh`: SLURM batch (native dtOO + enroot FEniCSx).
- `cluster/apptainer_fenicsx.def`: Container definition for enroot import.
- `cluster/env_notes.md`: Stack interaction notes.
- Local resonance-only: 7 evals, penalty 35.99 → 34.30, `output/optimization_multi.json`.
- Cluster: dtOO native ✅, enroot FEniCSx ✅, individually verified.
In Progress
- Cluster end-to-end `optimize_multi.py` loop (not yet run on cluster).
Blocked
- OF CFD case not built from dtOO state → `optimize_multi.py` degrades to resonance-only.
- `cfd_eval.py` column indices not validated against real `postProcessing/`.
- `rayleigh_ratios` NotImplementedError → wet frequencies use placeholder ~15 % shift.

Key Decisions
- (a) Penalty, not Pareto axis.
- (b) Dry now, wet later.
- Fixed band now, kinematic band later.
- eigenfrequencies repo, de_framework reference only.
- Sparse BC restriction (no densification).

Next Steps
1. Run `sbatch cluster/submit.sh` on cluster (start with `CFD_CASE_DIR=""` resonance-only).
2. Build OF CFD case from dtOO state (port `createStatesAndMeshes.CreateMeshes`).
3. Validate `cfd_eval.py` column indices on real cluster `postProcessing/`.
4. Calibrate mesh units: measure physical runner dims, compute scale factor.
5. Confirm hub-clamp physicality in ParaView (no near-zero rigid-body modes).
6. Test P2 (`element_degree=2`) on cluster node for accuracy vs memory.
7. Implement `added_mass.rayleigh_ratios` (dolfinx fluid-domain Laplace solve).
8. Auto-derive kinematic blade-passing band from `Z_guidevanes · n`.

Critical Context
- Active branch: `cfd-eigenfreq-multiobjective`.
- Remote: `git@github.com:RentschlerTobias/eigenfrequencies.git`.
- Last commit: `396282f` "handoff to track current prograss".
- enroot container: `pyxis_fenicsx` (dolfinx 0.11.0.post0).
- Cluster env file: `~/pe` (Python 3.13.3 + modules).
- dtOO case dir: `~/dtOO/build/test/tistos`.
- Cluster repo: `/pfs/work9/workspace/scratch/st_ac136362-eigenfreq/eigenfrequencies`.
- Forbidden band default: [100, 150] Hz (`OptimizationConfig.f_min / f_max`).
- Design params: `cV_ru_t_le_a_0.5`, `cV_ru_t_mid_a_0.5`, `cV_ru_t_te_a_0.5`.
- Mesh units WARNING: dtOO coords scaled (~2.5 bbox, not metres). Hz values and band may need rescaling.
- Solver: `RunnerModalSolver` with `BCConfig.mode="axial_plane"`, `axis="z"`, `plane_value=0.0`.
- CFD is optional: `CFD_CASE_DIR=""` → `optimize_multi.py` degrades to resonance-only.

Relevant Files
- `config.py` — All dataclasses.
- `dtoo_export.py` — STAGE 1: dtOO → runner.msh.
- `mesh_prep.py` — STAGE 2a: load + axis-discovery.
- `solver.py` — STAGE 2b: modal solver (sparse).
- `evaluate.py` — STAGE 2c: headless freq JSON.
- `main.py` — STAGE 2: full report + XDMF.
- `optimization.py` — Resonance penalty.
- `optimize.py` — STAGE 3 (legacy).
- `optimize_multi.py` — STAGE 3 (multi-objective host).
- `objective.py` — CFD scalar + resonance term.
- `cfd_eval.py` — OpenFOAM postProcessing reader.
- `added_mass.py` — Wet-mode interface + placeholder.
- `cluster/submit.sh` — SLURM batch.
- `cluster/apptainer_fenicsx.def` — Container definition.
- `cluster/env_notes.md` — Stack notes.
