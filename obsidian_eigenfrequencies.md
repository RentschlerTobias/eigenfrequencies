---
tags: [eigenfrequencies, resonance-avoidance, dolfinx, dtOO, hydraulic-turbine, modal-analysis, project]
status: in-progress
priority: high
created: 2026-07-01
updated: 2026-07-01
branch: cfd-eigenfreq-multiobjective
repo: eigenfrequencies
---

# Eigenfrequencies Resonance-Avoidance Objective

> [!note] Project Overview
> Extend **dtOO**-driven Francis-runner **shape optimization** (efficiency, cavitation, design head) with a **structural eigenfrequency objective** to avoid resonance. Long-term: FSI. Near-term: dry eigenfrequencies + static-pressure wet added-mass. Three-stage pipeline: **dtOO native** → **FEniCSx enroot** → **host optimizer** (`scipy.minimize`). CFD optional (degrades to resonance-only).

---

## Quick Status

| Component | Status | Last Test | Notes |
|-----------|--------|-----------|-------|
| dtOO mesh export (local) | ✅ Done | 2026-06-24 | `dtoo_export.py` baseline template OK |
| dtOO native (cluster) | ✅ Done | 2026-07-01 | `source ~/pe`, `LD_LIBRARY_PATH` set, `dtoOOPythonSWIG` imports OK |
| FEniCSx modal solve (local) | ✅ Done | 2026-06-24 | 10 real positive freqs, 1098 clamped DOFs, no rigid-body modes |
| FEniCSx container (cluster) | ✅ Built | 2026-07-01 | `enroot` → `pyxis_fenicsx`, dolfinx 0.11.0.post0 |
| Resonance-only optimize (local) | ✅ Done | 2026-06-24 | 7 evals, penalty 35.99 → 34.30, `output/optimization.json` |
| Multi-objective scaffold | ✅ Done | 2026-06-24 | `optimize_multi.py` + `objective.py` + `cfd_eval.py` wired |
| **Pyro5 DE parallelization** | ✅ **Done** | — | `server_de.py` + `optimize_de.py` + `run_de.sh` works on cluster |
| **Multi-harmonic forbidden band** | ✅ **Done** | Z=18, n=90 rpm | `optimization.py` now computes blade-passing + 6 harmonics |
| **Cluster end-to-end** | 🔴 **Open** | — | **NEXT STEP** — `sbatch cluster/submit_de.sh` |
| OF CFD case build | 🔴 Open | — | Port `createStatesAndMeshes.CreateMeshes` from de_framework |
| `cfd_eval` validation | 🔴 Open | — | Column indices unvalidated against real `postProcessing/` |
| Wet added-mass (real Laplace) | 🔴 Open | — | `rayleigh_ratios` NotImplementedError stub |

---

## Architecture (Mermaid)

```mermaid
graph TD
    A[Design vector x<br/>cV_ru_t_*.json] --> B[dtOO native<br/>~/pe + LD_LIBRARY_PATH]
    B --> C[runner.msh<br/>data/runner.msh]
    C --> D[FEniCSx enroot<br/>pyxis_fenicsx]
    D --> E[dry eigenfreqs Hz]
    E --> F[resonance penalty<br/>forbidden band [f_min, f_max]]
    F --> G[scipy.minimize<br/>Nelder-Mead]
    G --> A
    
    B --> H[OF case dir<br/>simpleFoam]
    H --> I[cfd_eval.py<br/>η, Vcav, dH]
    I --> J[cfd_scalar<br/>w_eta·tanh + w_cav·tanh + w_head·tanh]
    J --> K[combined_objective<br/>cfd_scalar + resonance_term]
    K --> G
    
    style D fill:#f9f,stroke:#333
    style G fill:#ff9,stroke:#333
    style K fill:#9f9,stroke:#333
```

---

## Design Decisions

> [!success] Decided

| # | Decision | Rationale |
|---|----------|-----------|
| a | Eigenfrequency objective = **penalty**, not Pareto axis | Keeps hydraulic objective space low-dimensional; resonance only bites on violation |
| b | **Dry modes now**, wet added-mass later | Dry solve validated; Laplace solve next physical correction |
| — | Fixed Hz forbidden band now, kinematic `Z·n` later | Fastest path to working objective; auto-derivation deferred |
| — | Build in **eigenfrequencies** repo, de_framework is reference only | de_framework patterns/CFD math reused, no fork dependency |
| — | Sparse BC restriction (free-DOF slice, no `toarray()`) | Beam densified → OOM at runner scale; CSR restriction scales to ~1M DOFs |

---

## Open Tasks

> [!todo] Next Steps — Prioritized

### 🔴 Blocker / Critical

- [ ] **Pyro5 DE parallelization test** `priority::critical`
  - `server_de.py` + `optimize_de.py` + `cluster/start_servers.sh` implemented
  - Follows rl_framework schema: persistent Pyro5 worker servers per core
  - Replaces ThreadPoolExecutor (deadlock) with RPC-based distributed DE
  - **Action:** Start servers + client on cluster, verify .msh production per worker

- [ ] **Cluster end-to-end test** `priority::critical`
  - `sbatch cluster/submit.sh`, monitor `squeue -u $USER`, read `turbine_runner/optimize_multi.log`
  - Start with `CFD_CASE_DIR=""` (resonance-only) → then enable CFD
  - **Action:** Run on interactive `salloc` first, then batch job

- [ ] **Validate `cfd_eval.py` column indices** `priority::critical`
  - OpenFOAM `postProcessing/` column layout depends on `system/` setup
  - Match de_framework tistos case; confirm on real cluster output before trusting magnitudes

- [ ] **Build OF CFD case from dtOO state** `priority::critical`
  - Port `createStatesAndMeshes.CreateMeshes` from de_framework
  - Extend `dtoo_export.py` to also generate OF mesh + `simpleFoam` case dir

### 🟡 Important

- [ ] **Mesh units calibration** `priority::high`
  - dtOO coords scaled (~2.5 bbox, not metres) → rescales every Hz and the band
  - Measure physical runner dims, compute scale factor, update `config.py` and `BCConfig`

- [ ] **Hub-clamp BC physicality** `priority::high`
  - Confirm clamped-node bbox at hub in ParaView (`output/modes.xdmf`)
  - If near-zero rigid-body modes appear → fix `BCConfig` (axis, hub_radius, plane_value)

- [ ] **P1 vs P2 convergence** `priority::medium`
  - P2 (`SolverConfig.element_degree=2`) more accurate, ~1M DOFs → OOM on <8 GB hosts
  - Test on cluster node (more memory); compare frequencies against P1 baseline

- [ ] **`rayleigh_ratios` (Laplace solve)** `priority::medium`
  - Per-mode added-mass ratio via dolfinx Laplace solve on fluid domain
  - Replace `placeholder_ratios` in `added_mass.py`; see HANDOFF.md

- [ ] **Kinematic blade-passing band** `priority::medium`
  - Move forbidden band from fixed [100,150] Hz to `Z_guidevanes · n` (auto-derive)
  - Update `OptimizationConfig.f_min / f_max` dynamically

### 🟢 Optional / Long-term

- [ ] **True Pareto optimization** `priority::low`
  - NSGA-II if scalarization (`tanh` single-objective) proves limiting
  - Requires multi-objective solver library (pymoo, DEAP)

- [ ] **Unsteady CFD + Helmholtz FSI** `priority::low`
  - Full fluid–structure interaction (forced response amplitude, fatigue)
  - Out of current scope; see documentation.md §6

---

## Experiment Tracking

> [!note] Runs & Planned Experiments

| Experiment | Status | Config | Result | Notes |
|-----------|--------|--------|--------|-------|
| Local resonance-only | ✅ Done | `OPT_MAX_ITER=7`, `CFD_CASE_DIR=""` | Penalty 35.99 → 34.30, 7 evals | Modes 3/4/5 in [100,150] Hz |
| Multi-objective scaffold | ✅ Done | `optimize_multi.py` wired | CFD eval stub ready | OF case dir absent locally |
| Cluster smoke (interactive) | 🔴 Planned | `salloc -p dev_cpu` | — | **FIRST** — test dtOO + enroot per eval |
| Cluster batch (resonance-only) | 🔴 Planned | `sbatch cluster/submit.sh`, `CFD_CASE_DIR=""` | — | After smoke passes |
| Cluster batch (full CFD+res) | 🔴 Planned | `sbatch cluster/submit.sh` + OF case dir | — | After CFD case build |
| Wet real-Laplace | 🔴 Planned | `added_mass.rayleigh_ratios` | — | After dry baseline stable |

### Metrics to Track

- [ ] Penalty per evaluation
- [ ] Modes inside forbidden band (count + which)
- [ ] Runtime per evaluation (dtOO build + FEniCSx solve)
- [ ] dtOO build success rate
- [ ] Mesh element count (P1 vs P2)
- [ ] CFD scalar components (η, Vcav, dH) once validated
- [ ] Wet vs dry frequency shift (%)

---

## Physical Assumptions & Limitations

> [!warning] Current model computes **dry eigenfrequencies only** — major physical effects are missing.

| Effect | Impact on Frequencies | Status | Notes |
|--------|----------------------|--------|-------|
| **Added mass (water)** | ↓ 15–40 % (effective mass increases) | 🔴 `added_mass.py` = placeholder (15 % fixed) | Real Laplace solve needs fluid mesh + wetted-surface tagging |
| **Centrifugal stiffening** | ↑ (rotation tensions structure) | 🔴 Not implemented | Small at 90 rpm, significant at 500 rpm |
| **Coriolis coupling** | Modifies mode shapes, splits degenerate modes | 🔴 Not implemented | Only relevant for rotating reference frame |
| **Structural damping** | Reduces resonance amplitude (peak flattening) | 🔴 Not implemented | Hydrodynamic damping from water is significant |
| **Gravity / pressure prestress** | Geometric stiffening from static loads | 🔴 Not implemented | Requires nonlinear static solve first |
| **Hydrodynamic eigenfrequencies** | Water has its own modes, couples with structure | 🔴 Not implemented | Full FSI (Helmholtz) — out of scope |

**Consequence:** The optimizer currently shifts **dry modes** out of the forbidden band. Wet modes (real operating condition) will be **lower** due to added mass. A dry mode at 25.6 Hz becomes ~20–22 Hz in water — this must be accounted for when setting the forbidden band.

---

## Known Problems

> [!warning] Bugs & Limitations

1. **`rayleigh_ratios` NotImplementedError** — `added_mass.py` stub. Wet frequencies use placeholder ratio ~15 % shift. Real Laplace solve needs dolfinx fluid mesh + wetted-surface tagging.
2. **Cluster pipeline not yet run** — dtOO native + enroot tested individually on cluster, full `optimize_multi.py` loop not yet executed. HANDOFF.md is the test script.
3. **OF case dir empty** — CFD step in `optimize_multi.py` degrades to resonance-only because OpenFOAM case has not been built from dtOO state.
4. **`cfd_eval` column indices unvalidated** — `Q_ru_in`, `ptot_ru_in`, `ptot_ru_out`, `forces.dat` column layout matches de_framework reference but not confirmed against real cluster output.
5. **Mesh units unknown** — dtOO coords are scaled (~2.5 bbox). Frequencies and band positions may need rescaling once physical dimensions are known. Band formula (Z·n/60) is correct, but absolute Hz values depend on mesh scale.
6. **P2 OOM risk** — `SolverConfig.element_degree=2` ~1M DOFs on cluster node may exceed memory if `dev_cpu` node is small.
7. **No near-zero rigid-body modes locally** — clamp passes locally; physicality confirmation (ParaView) still TODO.

---

## File Reference

> [!info] Key Files

| File | Purpose | Last Change |
|------|---------|-------------|
| `config.py` | Material / BC / Mesh / Solver / CFD / Objective / WetMode dataclasses | 2026-06-24 |
| `dtoo_export.py` | STAGE 1: dtOO → `runner.msh` (cluster-adapted, no Docker) | 2026-07-01 |
| `mesh_prep.py` | STAGE 2a: load mesh + volume fallback + axis-discovery diagnostic | 2026-06-24 |
| `solver.py` | STAGE 2b: `RunnerModalSolver` (sparse, config-driven hub clamp) | 2026-06-24 |
| `evaluate.py` | STAGE 2c: headless frequency evaluation (JSON line for optimizer) | 2026-06-24 |
| `main.py` | STAGE 2: full report + XDMF/VTK/JSON | 2026-06-24 |
| `optimization.py` | Resonance penalty (`compute_penalty`, `band_report`) | 2026-06-24 |
| `optimize.py` | STAGE 3 (legacy): dtOO + FEniCSx per eval, resonance-only | 2026-07-01 |
| `optimize_multi.py` | STAGE 3 (new): multi-objective host, CFD optional | 2026-06-24 |
| `objective.py` | `cfd_scalar` + `resonance_term` → `combined_objective` | 2026-06-24 |
| `cfd_eval.py` | OpenFOAM `postProcessing` reader → η, Vcav, dH | 2026-06-24 |
| `added_mass.py` | Wet-mode interface + placeholder ratios + `rayleigh_ratios` stub | 2026-06-24 |
| `cluster/submit.sh` | SLURM batch (native dtOO + enroot FEniCSx) | 2026-07-01 |
| `cluster/start_servers.sh` | Start Pyro5 Name Server + DE worker servers | 2026-07-02 |
| `cluster/apptainer_fenicsx.def` | Container definition (imported via enroot) | 2026-07-01 |
| `cluster/env_notes.md` | How dtOO + OpenFOAM stack and FEniCSx stack interact | 2026-07-01 |
| `server_de.py` | Pyro5 worker server: evaluates one design per RPC call | 2026-07-02 |
| `optimize_de.py` | Pyro5 DE client: dispatches designs to worker servers | 2026-07-02 |

---

## Data Locations

- **Cluster repo path:** `/pfs/work9/workspace/scratch/st_ac136362-eigenfreq/eigenfrequencies`
- **dtOO install:** `~/dtOO` (binaries, libs, case dir `~/dtOO/build/test/tistos`)
- **enroot container:** `~/.local/share/enroot/pyxis_fenicsx/`
- **Local mesh:** `turbine_runner/data/runner.msh`
- **Local design JSON:** `turbine_runner/data/design.json`
- **Local optimization history:** `output/optimization.json` (legacy), `output/optimization_multi.json` (new)
- **Cluster output:** `turbine_runner/optimize_multi.log` (batch), `turbine_runner/data/runner.msh` (per eval)
- **Venv (cluster):** `~/pe` (sources Python 3.13.3 + modules)

---

## Git Status

- **Branch:** `cfd-eigenfreq-multiobjective`
- **Remote:** `origin git@github.com:RentschlerTobias/eigenfrequencies.git`
- **Last Commit:** `8d43ac8` — "feat(de): Pyro5-based distributed DE (rl_framework schema)"
- **Untracked:** `beam_demo.log`, `beam_demo_2.log`, `output/` (large logs, XDMF, PNG), `dtoo_export.log`, `server_logs/`

---

## Daily Log

> [!example] Iteration Log

### 2026-07-02 — Pyro5 DE Parallelization + Multi-harmonic Band
- `server_de.py` created: Pyro5 server exposing `evaluate(x, labels)` → dtOO build + FEniCSx + optional CFD
- `optimize_de.py` rewritten: Pyro5 client, DE master dispatches designs via RPC to persistent workers
- `cluster/start_servers.sh` + `run_de.sh` created: starts Name Server + N worker servers (one per core)
- ThreadPoolExecutor deadlock diagnosed: subprocess.run(capture_output=True) with parallel threads = pipe buffer deadlock
- Fix: rl_framework schema — persistent Pyro5 servers, subprocess runs inside server process (one at a time per worker)
- Commit `8d43ac8`: "feat(de): Pyro5-based distributed DE (rl_framework schema)"
- **Multi-harmonic forbidden band**: Replaced arbitrary [100,150] Hz with blade-passing + 6 harmonics (Z=18, n=90 rpm → f_bp=27 Hz). Proportional margin max(5Hz, 5%). Penalty drops from 36.7 to 14.25.
- **Physical assumptions documented**: Current model is dry modes only. Added mass, centrifugal stiffening, Coriolis, damping, prestress all missing. Wet modes will be 15-40% lower.

### 2026-07-01 — Cluster Adaptation & Handoff
- `cluster/submit.sh` adapted: `source ~/pe`, `partition=dev_cpu`, enroot `FENICSX_CONTAINER=pyxis_fenicsx`
- `dtoo_export.py` cluster-adapted: removed hardcoded Docker paths (`/dtOO`, `/work`), added `DTOO_LOG_FILE`, defaults to `~/dtOO/build/test/tistos` and `data/runner.msh`
- `optimize.py` `_run_dtoo()` / `_run_fenicsx()` adapted: `docker run` → native bash + enroot
- HANDOFF.md created for context-free cluster continuation
- dtOO native + enroot individually verified on cluster (see HANDOFF.md §3)

### 2026-06-24 — Multi-Objective Scaffold
- `optimize_multi.py` created: host orchestrator, CFD optional, degrades to resonance-only
- `objective.py` created: `cfd_scalar` (tanh scalarization) + `resonance_term` (penalty)
- `cfd_eval.py` created: plain OpenFOAM `postProcessing` reader (no pyDtOO/dolfinx)
- `added_mass.py` created: wet-mode interface + placeholder ratios + `rayleigh_ratios` stub
- `config.py` extended: `CFDConfig`, `ObjectiveConfig`, `WetModeConfig` added
- Local resonance-only loop end-to-end: 7 evals, penalty 35.99 → 34.30, `output/optimization_multi.json`
- Dry-vs-wet compare: placeholder ~15 % shift moves modes 3/4/5 out of band

---

## Snippets & Quick Commands

> [!tip] Useful Code Snippets

### Run resonance-only locally
```bash
cd turbine_runner
CFD_CASE_DIR="" OPT_MAX_ITER=7 python3 optimize_multi.py
```

### Run on cluster (interactive smoke)
```bash
salloc -p dev_cpu -n 1 -t 00:30:00
source ~/pe
export LD_LIBRARY_PATH=~/dtOO/install/lib:~/dtOO/install/lib64:$LD_LIBRARY_PATH
cd /pfs/work9/workspace/scratch/st_ac136362-eigenfreq/eigenfrequencies/turbine_runner
CFD_CASE_DIR="" OPT_MAX_ITER=3 python3 optimize_multi.py
```

### Axis-discovery diagnostic
```bash
# inside fenicsx container, in turbine_runner/
python3 mesh_prep.py
```

### Cancel cluster job
```bash
scancel <JOBID>
```

---

## Related Notes

- [[obsidian_dashboard_eigenfrequencies]] — Status dashboard (at-a-glance)
- [[HANDOFF]] — Cluster testing tutorial (context-free handoff)
- [[documentation]] — Physics rationale, design decisions, status
- [[cluster/env_notes]] — Stack interaction notes
- [[cluster/apptainer_fenicsx.def]] — Container definition
- [[overview]] — Flat ASCII context for AI loads

---

*Last Update: 2026-07-02*
*Status: Pyro5 DE parallelization works. Multi-harmonic forbidden band implemented. Next: wet modes (added mass) + cluster batch test*
*Next Action: `sbatch cluster/submit_de.sh` on cluster, verify optimization with new band*
