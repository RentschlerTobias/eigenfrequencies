# HANDOFF — cluster testing of the CFD + eigenfrequency runner optimization

Audience: a **context-free agent** picking this up to test on **bwUniCluster 3.0**.
Read this top to bottom before touching anything. Companion: `documentation.md` (why),
`cluster/env_notes.md` (how the two software stacks fit).

## 0. Gotchas that already bit this project (read first)

- **Repo paths.** The reference optimization is at **`/root/repos/de_framework`**, NOT
  `/repos/de_framework` (that path does not exist). The target/work repo is
  **`/root/repos/eigenfrequencies`**.
- **de_framework real code is on branch `origin/bwCl`**, not the checked-out `main`
  (which has only 6 files). Inspect with `git show origin/bwCl:<file>`.
- **Never chain `cd <dir> && <destructive>`** — a silent `cd` failure lands the command in
  the wrong repo. It mis-explored twice here. Verify `pwd`/`ls -d` first; use absolute paths.
- **No Claude/AI attribution** in any commit, code, or PR (project rule).

## 1. What this branch contains (`cfd-eigenfreq-multiobjective`)

Target repo `eigenfrequencies/turbine_runner/`:

| File | State | Role |
|------|-------|------|
| `config.py` | extended | `+CFDConfig, +ObjectiveConfig, +WetModeConfig` |
| `objective.py` | new | combined CFD + resonance objective (scalarized, resonance = penalty) |
| `cfd_eval.py` | new | OpenFOAM `postProcessing` reader → η, Vcav, dH, P, Q |
| `added_mass.py` | new | wet-mode interface; Laplace solve **stubbed** (placeholder ratios) |
| `solver.py` | extended | `+wet_compare()`; dry modal solve unchanged |
| `optimize_multi.py` | new | host loop: dtOO → CFD + modal → combined objective |
| `cluster/submit.sh`, `apptainer_fenicsx.def`, `env_notes.md` | new | SLURM + dolfinx image + env |
| `dtoo_export.py`, `mesh_prep.py`, `evaluate.py`, `optimization.py` | reused | dry pipeline (works) |

**What is real vs pending:** the dry modal pipeline + resonance penalty work and have run
end-to-end locally (`output/frequencies.json`, `output/optimization.json`). The CFD-objective
math is **ported but unvalidated** without live `simpleFoam`. Wet modes are **interface-only**
(placeholder ratios; real Laplace solve is `added_mass.rayleigh_ratios`, NotImplementedError).

## 2. Bring-up on bwUniCluster 3.0

1. **dolfinx image (modal solve).** On a box with apptainer:
   `apptainer build eigenfrequencies-fenicsx.sif cluster/apptainer_fenicsx.def`.
   Copy the `.sif` to the cluster; set `FENICSX_SIF` (see `cluster/submit.sh`).
2. **dtOO + OpenFOAM env.** `source ~/de` (or `. dtoo of_v2406_15.6`), plus
   `export OSLO_LOCK_PATH=/tmp; export FOAM_SIGFPE=0`. Confirm `dtOOPythonSWIG`,
   `simpleFoam`, `decomposePar` resolve.
3. **dtOO builds BOTH meshes.** `dtoo_export.py` writes the mech mesh (`runner.msh`). The CFD
   case still needs the OF case dir from the **same** dtOO state — port de_framework
   `tistos_files/createStatesAndMeshes.py:CreateMeshes` (`dC.get('tistos_ru_of_n').runCurrentState()`)
   into a CFD-export step so `CFD_CASE_DIR` is populated.
4. **Wire modal solve through apptainer.** `optimize.py:_run_fenicsx()` calls `docker run`;
   replace with `apptainer exec --bind "$REPO:/workspace" "$FENICSX_SIF" python3 …`,
   keeping the `RESULT_JSON` stdout contract. See `cluster/env_notes.md`.

## 3. Run

- **Resonance-only smoke test (no CFD)** — fastest sanity check:
  `CFD_CASE_DIR="" OPT_MAX_ITER=3 python3 turbine_runner/optimize_multi.py`
  → expect per-eval objective = resonance penalty; 0 unless a mode is in `[100,150] Hz`.
- **Full run on the cluster:** `sbatch cluster/submit.sh`
  (env: `OPT_FMIN/OPT_FMAX/OPT_MAX_ITER`, `CFD_CASE_DIR`, `FENICSX_SIF`).
  Results → `turbine_runner/output/optimization_multi.json`.

## 4. Validation checklist (do not trust numbers until these pass)

1. **Mesh units** — dtOO coords are scaled (~2.5 bbox, not metres). Eigenfrequency magnitude
   scales with size → confirm the export unit and rescale in `mesh_prep` if needed. This also
   rescales the forbidden band (`OptimizationConfig.f_min/f_max`).
2. **Hub-clamp BC** — `BCConfig` defaults clamp the `z=0` plane (smoke-test). Confirm that is the
   real shaft attachment in ParaView (`output/modes.pvd`, Warp By Vector; clamped face stays fixed).
3. **No rigid-body modes** — solver logs must show fixed DOFs > 0 and no near-zero frequencies.
4. **P1 vs P2** — default P1 (`SolverConfig.element_degree=1`) is slightly stiff (freqs a bit high);
   P2 OOMs on small hosts but is fine on cluster nodes — run a P2 convergence check.
5. **CFD columns** — verify `cfd_eval.py` field/column indices against a real `postProcessing/`
   dump (Q_ru_in, ptot_ru_in/out, forces, V_CAV) before trusting η/Vcav/dH.
6. **Wet < dry** — once `rayleigh_ratios` is implemented, confirm wet frequencies are below dry
   and the shift is physically plausible (~20–40 %).

## 5. Reading results

- `output/frequencies.json` — dry eigenfrequencies of the last evaluated design.
- `output/optimization_multi.json` — `{best_design, best_objective, history[]}` with per-eval
  `f_cfd`, `f_resonance`, η, Vcav, dH, and the resonance band report.
- de_framework analogues for comparison: per-state `runData*/{P,dH,eta,VCav}.<id>`.

## 6. Next physics step after this works

Implement `added_mass.rayleigh_ratios` (level-1 Laplace added mass) → wet modes; then move the
forbidden band from a fixed Hz window to kinematic blade-passing lines (`Z_guidevanes · n`).
FSI (Helmholtz ↔ elasticity, forced-response amplitude) is the milestone after that.
