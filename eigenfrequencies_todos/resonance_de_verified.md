---
status: verified
scope: resonance-only DE pipeline on bwUniCluster 3.0 — dtOO + FEniCSx modal, no CFD
related_files:
  - turbine_runner/optimize_de.py
  - turbine_runner/server_de.py
  - turbine_runner/start_servers.sh
  - turbine_runner/optimize.py
  - turbine_runner/optimization.py
  - turbine_runner/config.py
  - turbine_runner/objective.py
  - cluster/submit_de.sh
  - cluster/env_notes.md
detail_of: "[[obsidian_dashboard_eigenfrequencies#1. Resonance-only DE — cluster-verified]]"
---

# Resonance-only DE — cluster-verified

Cluster end-to-end confirmed (HANDOFF §2). Pyro5 persistent workers, file-based URI discovery on shared FS, checkpoint/resume, live progress, fitness metrics per generation. Local run still works (penalty 35.99 → 34.30, 7 evals, modes 3/4/5 in band).

## Done

- [x] Local resonance-only end-to-end (penalty 35.99→34.30, 7 evals)
- [x] Pyro5 worker servers (`server_de.py` + `start_servers.sh`) — replaced ThreadPoolExecutor deadlock
- [x] A2 file-based URI discovery (`$DE_URI_DIR/worker_<id>.uri`, atomic writes)
- [x] dtOO native + enroot FEniCSx container
- [x] Checkpoint/resume (`de_state.json`, atomic per gen, `DE_FRESH=1`)
- [x] Live-view (tqdm + `de_history.jsonl`, `DE_TQDM_INTERVAL`)
- [x] Fitness metrics per generation (eta/vcav/f_resonance/freqs in logs + jsonl)
- [x] Convergence fix: stop on `std(objectives ohne Penalty) < tol` (was `std(span)` — constant bounds)
- [x] XDG_RUNTIME_DIR=/tmp fix for enroot (MPI / PMIx writable)
- [x] Multi-harmonic forbidden band (Z=18, n=90 rpm)
- [x] Cluster resonance-only verified — objective ~5.3 on bwUniCluster 3.0

## Open

- [ ] Mesh-units scale factor (cluster run completed with current scaling; absolute Hz unknown)
- [ ] Hub-clamp BC physicality (ParaView confirm — near-zero rigid-body modes should be absent)

## Reference

- HANDOFF §2 (cluster-verified claims), §4 (chronology of fixes)
- PROGRESS Phase 1+2 (core + cluster integration)

## Context from obsidian_eigenfrequencies.md

### Quick Status (DE-related)

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

### Open Tasks

- [ ] **Pyro5 DE parallelization test** `priority::critical`
  - `server_de.py` + `optimize_de.py` + `cluster/start_servers.sh` implemented
  - Follows rl_framework schema: persistent Pyro5 worker servers per core
  - Replaces ThreadPoolExecutor (deadlock) with RPC-based distributed DE
  - **Action:** Start servers + client on cluster, verify .msh production per worker

- [ ] **Cluster end-to-end test** `priority::critical`
  - `sbatch cluster/submit.sh`, monitor `squeue -u $USER`, read `turbine_runner/optimize_multi.log`
  - Start with `CFD_CASE_DIR=""` (resonance-only) → then enable CFD
  - **Action:** Run on interactive `salloc` first, then batch job

### Experiment Tracking

| Experiment | Status | Config | Result | Notes |
|-----------|--------|--------|--------|-------|
| Local resonance-only | ✅ Done | `OPT_MAX_ITER=7`, `CFD_CASE_DIR=""` | Penalty 35.99 → 34.30, 7 evals | Modes 3/4/5 in [100,150] Hz |
| Multi-objective scaffold | ✅ Done | `optimize_multi.py` wired | CFD eval stub ready | OF case dir absent locally |
| Cluster smoke (interactive) | 🔴 Planned | `salloc -p dev_cpu` | — | **FIRST** — test dtOO + enroot per eval |
| Cluster batch (resonance-only) | 🔴 Planned | `sbatch cluster/submit.sh`, `CFD_CASE_DIR=""` | — | After smoke passes |

### Metrics to Track

- [ ] Penalty per evaluation
- [ ] Modes inside forbidden band (count + which)
- [ ] Runtime per evaluation (dtOO build + FEniCSx solve)
- [ ] dtOO build success rate
- [ ] Mesh element count (P1 vs P2)
- [ ] CFD scalar components (η, Vcav, dH) once validated
- [ ] Wet vs dry frequency shift (%)

### Daily Log

#### 2026-07-02 — Pyro5 DE Parallelization + Multi-harmonic Band
- `server_de.py` created: Pyro5 server exposing `evaluate(x, labels)` → dtOO build + FEniCSx + optional CFD
- `optimize_de.py` rewritten: Pyro5 client, DE master dispatches designs via RPC to persistent workers
- `cluster/start_servers.sh` + `run_de.sh` created: starts Name Server + N worker servers (one per core)
- ThreadPoolExecutor deadlock diagnosed: subprocess.run(capture_output=True) with parallel threads = pipe buffer deadlock
- Fix: rl_framework schema — persistent Pyro5 servers, subprocess runs inside server process (one at a time per worker)
- Commit `8d43ac8`: "feat(de): Pyro5-based distributed DE (rl_framework schema)"
- **Multi-harmonic forbidden band**: Replaced arbitrary [100,150] Hz with blade-passing + 6 harmonics (Z=18, n=90 rpm → f_bp=27 Hz). Proportional margin max(5Hz, 5%). Penalty drops from 36.7 to 14.25.
- **Physical assumptions documented**: Current model is dry modes only. Added mass, centrifugal stiffening, Coriolis, damping, prestress all missing. Wet modes will be 15-40% lower.

#### 2026-07-01 — Cluster Adaptation & Handoff
- `cluster/submit.sh` adapted: `source ~/pe`, `partition=dev_cpu`, enroot `FENICSX_CONTAINER=pyxis_fenicsx`
- `dtoo_export.py` cluster-adapted: removed hardcoded Docker paths (`/dtOO`, `/work`), added `DTOO_LOG_FILE`, defaults to `~/dtOO/build/test/tistos` and `data/runner.msh`
- `optimize.py` `_run_dtoo()` / `_run_fenicsx()` adapted: `docker run` → native bash + enroot
- HANDOFF.md created for context-free cluster continuation
- dtOO native + enroot individually verified on cluster (see HANDOFF.md §3)

#### 2026-06-24 — Multi-Objective Scaffold
- `optimize_multi.py` created: host orchestrator, CFD optional, degrades to resonance-only
- `objective.py` created: `cfd_scalar` (tanh scalarization) + `resonance_term` (penalty)
- `cfd_eval.py` created: plain OpenFOAM `postProcessing` reader (no pyDtOO/dolfinx)
- `added_mass.py` created: wet-mode interface + placeholder ratios + `rayleigh_ratios` stub
- `config.py` extended: `CFDConfig`, `ObjectiveConfig`, `WetModeConfig` added
- Local resonance-only loop end-to-end: 7 evals, penalty 35.99 → 34.30, `output/optimization_multi.json`
- Dry-vs-wet compare: placeholder ~15 % shift moves modes 3/4/5 out of band

### Snippets

#### Run resonance-only locally
```bash
cd turbine_runner
CFD_CASE_DIR="" OPT_MAX_ITER=7 python3 optimize_multi.py
```

#### Run on cluster (interactive smoke)
```bash
salloc -p dev_cpu -n 1 -t 00:30:00
source ~/pe
export LD_LIBRARY_PATH=~/dtOO/install/lib:~/dtOO/install/lib64:$LD_LIBRARY_PATH
cd /pfs/work9/workspace/scratch/st_ac136362-eigenfreq/eigenfrequencies/turbine_runner
CFD_CASE_DIR="" OPT_MAX_ITER=3 python3 optimize_multi.py
```

### File Reference

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

### Data Locations

- **Cluster repo path:** `/pfs/work9/workspace/scratch/st_ac136362-eigenfreq/eigenfrequencies`
- **dtOO install:** `~/dtOO` (binaries, libs, case dir `~/dtOO/build/test/tistos`)
- **enroot container:** `~/.local/share/enroot/pyxis_fenicsx/`
- **Local mesh:** `turbine_runner/data/runner.msh`
- **Local design JSON:** `turbine_runner/data/design.json`
- **Local optimization history:** `output/optimization.json` (legacy), `output/optimization_multi.json` (new)
- **Cluster output:** `turbine_runner/optimize_multi.log` (batch), `turbine_runner/data/runner.msh` (per eval)
- **Venv (cluster):** `~/pe` (sources Python 3.13.3 + modules)

### Git Status

- **Branch:** `main` (merged `cfd-eigenfreq-multiobjective` 2026-07-02)
- **Remote:** `origin git@github.com:RentschlerTobias/eigenfrequencies.git`
- **Last Commit:** `d55c1d3` — "docs(obsidian): update dashboard with multi-harmonic band status"
- **Untracked:** `beam_demo.log`, `beam_demo_2.log`, `output/` (large logs, XDMF, PNG), `dtoo_export.log`, `server_logs/`

### Architecture (Mermaid)

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
