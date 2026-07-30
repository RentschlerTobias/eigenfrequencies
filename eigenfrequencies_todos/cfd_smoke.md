---
status: wired_unverified
scope: CFD solve path end-to-end on a single node — verify OF case builds, simpleFoam converges, column mapping in cfd_eval.py matches real postProcessing
related_files:
  - turbine_runner/dtoo_cfd_build.py
  - turbine_runner/cfd_eval.py
  - turbine_runner/optimize.py (`_run_cfd`)
  - turbine_runner/objective.py (`combined_objective`)
  - turbine_runner/config.py (`CFDConfig`)
  - cfd/tistos_files/
  - cfd/xml/tistos_ru_of.xml
  - cluster/submit_de.sh
  - cluster/apptainer_fenicsx.def
detail_of: "[[obsidian_dashboard_eigenfrequencies#2. CFD solve smoke — wired, unverified]]"
---

# CFD solve smoke — wired, unverified

COMMIT `a0c0676` wired the full CFD path: each worker stages an OF case via `dtoo_cfd_build.py` (templateState + `CreateStates`+`CreateMeshes`), runs `simpleFoam` via `sbatch.tistos_ru_of.sh`, `cfd_eval.py` reads `postProcessing/<fo>/100`. Need a smoke run to confirm.

## Sub-items

- [ ] Submit smoke: `sbatch --partition=cpu_il --nodes=1 --ntasks-per-node=2 --cpus-per-task=16 --time=01:00:00 --export=ALL,DE_POP_SIZE=2,DE_MAX_GEN=1,DE_FRESH=1 cluster/submit_de.sh`
- [ ] Inspect `server_logs/worker_0.log` — confirm `_run_cfd` success
- [ ] Inspect `$TMPDIR/worker_0/cfd_build.log` and `cfd_solve.log`
- [ ] Confirm `de_history.jsonl` shows real eta/vcav/dH (not `DTOO_FAIL_PENALTY = 1e6`)
- [ ] Validate `cfd_eval.py` column indices against real `postProcessing/` dump — esp. `moment.dat` total-z (index 3 assumption for forces)
- [ ] Confirm functionObject names emitted in `cfd/xml/tistos_ru_of.xml`: `Q_ru_in`, `ptot_ru_in`, `ptot_ru_out`, `forces`, `V_CAV`

## Implementation notes

- `_run_cfd` has `CFD_TIMEOUT=1800s`; `_run_dtoo`/`_run_fenicsx` have no timeout (see [[eigenfrequencies_todos/cluster_robustness]])
- Env hardening: `FOAM_SIGFPE=0`, `OSLO_LOCK_PATH=/tmp`, `XDG_RUNTIME_DIR=/tmp`, `TMPDIR=/tmp`
- Reuses de_framework tistos machinery (template/case build)
- `DesignConfig`: 3 DoF `cV_ru_t_le_a_{0.5,mid,te}`
- `CFDConfig`: `post_folder="100"`, `end_time=500`, `omega`, `rho`, `g`

## Reference

- HANDOFF §2 (wired, smoke pending), §5 (blocker), §6 (smoke command)

## Context from obsidian_eigenfrequencies.md

### Quick Status (CFD-related)

| Component | Status | Last Test | Notes |
|-----------|--------|-----------|-------|
| OF CFD case build | 🔴 Open | — | Port `createStatesAndMeshes.CreateMeshes` from de_framework |
| `cfd_eval` validation | 🔴 Open | — | Column indices unvalidated against real `postProcessing/` |

### Open Tasks

- [ ] **Validate `cfd_eval.py` column indices** `priority::critical`
  - OpenFOAM `postProcessing/` column layout depends on `system/` setup
  - Match de_framework tistos case; confirm on real cluster output before trusting magnitudes

- [ ] **Build OF CFD case from dtOO state** `priority::critical`
  - Port `createStatesAndMeshes.CreateMeshes` from de_framework
  - Extend `dtoo_export.py` to also generate OF mesh + `simpleFoam` case dir

### Known Problems

1. **OF case dir empty** — CFD step in `optimize_multi.py` degrades to resonance-only because OpenFOAM case has not been built from dtOO state.
2. **`cfd_eval` column indices unvalidated** — `Q_ru_in`, `ptot_ru_in`, `ptot_ru_out`, `forces.dat` column layout matches de_framework reference but not confirmed against real cluster output.
