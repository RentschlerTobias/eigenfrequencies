# Implementation Progress: DE Parallelization

> Last updated: 2026-07-01
> Status: PHASE 1 COMPLETE — Core DE implementation done, ready for smoke testing.

## Decisions (Locked)

- **Optimizer**: Differential Evolution (DE) replaces Nelder-Mead
- **Parallelization**: Single node, 20 workers × 1 core
- **I/O isolation**: `$TMPDIR/worker_{id}/` per worker
- **DE implementation**: Custom loop + `ProcessPoolExecutor(start_method='spawn')`
- **OpenFOAM/FEniCSx parallel**: Deferred (1-core for now)

## Hardware Context

- **Partition**: `cpu` (not `dev_cpu` for production runs)
- **Node**: AMD EPYC 9454, 96 physical cores, 384 GB RAM, 3.84 TB NVMe
- **dev_cpu limit**: 1 node, 30 min walltime — for smoke tests only
- **cpu limit**: 20 nodes, 72h walltime

## Checklist

### Phase 1: Core DE Implementation ✅

- [x] Create `turbine_runner/optimize_de.py` — custom DE loop with ProcessPoolExecutor
  - [x] DE parameters: pop_size=20, F=0.8, CR=0.9, max_generations=30
  - [x] Worker function with `$TMPDIR/worker_{id}/` paths
  - [x] Error handling: failed design → penalty, continue generation
  - [x] Picklable worker for `spawn` compatibility
  - [x] Supports both resonance-only and full CFD modes
- [x] Modify `turbine_runner/optimize.py`
  - [x] `_run_dtoo(design, worker_id=0)` — uses `$TMPDIR/worker_{id}/`
  - [x] `_run_fenicsx(worker_id=0)` — reads from worker directory
  - [x] `_run_dtoo()` backward-compatible (default worker_id=0)
  - [x] Enroot mount: worker directory mounted as `/worker_data` in container
- [x] Modify `turbine_runner/config.py`
  - [x] Added `DEConfig` dataclass with pop_size, mutation, crossover, max_generations, tol, seed
  - [x] Kept existing `OptimizationConfig` for backward compatibility

### Phase 2: Cluster Integration ✅

- [x] Modify `cluster/submit.sh`
  - [x] Switch partition from `dev_cpu` to `cpu`
  - [x] Request 20 tasks (`--ntasks=20 --cpus-per-task=1`)
  - [x] Extend walltime to 8 hours for full DE run
  - [x] Run `optimize_de.py` instead of `optimize_multi.py`
  - [x] DE env vars: DE_POP_SIZE, DE_MUTATION, DE_CROSSOVER, DE_MAX_GEN, DE_TOL, DE_SEED
- [x] Create `cluster/submit_dev.sh` — smoke test script for `dev_cpu`
  - [x] 4 tasks, 3 generations, 30 min, no CFD
  - [x] Fixed seed (42) for reproducible smoke tests

### Phase 3: Testing 🔄 READY

- [ ] Smoke test on `dev_cpu`: `sbatch cluster/submit_dev.sh`
  - [ ] Verify 4 workers spawn
  - [ ] Verify `$TMPDIR/worker_{id}/` isolation (no file collisions)
  - [ ] Verify DE runs without crash
  - [ ] Check `output/optimization_de.json` produced
- [ ] Production test on `cpu`: `sbatch cluster/submit.sh`
  - [ ] Monitor `squeue` for job status
  - [ ] Check `turbine_runner/optimize_de.log`
  - [ ] Validate output frequencies reasonable

### Phase 4: Optimization & Follow-ups (Deferred)

- [ ] **OpenFOAM parallel**: `decomposeParDict` + `mpirun simpleFoam -parallel`
- [ ] **FEniCSx parallel**: SLEPc/primme for eigenvalue solve
- [ ] **P2 convergence**: `SolverConfig.element_degree=2` (test on high-mem node)
- [ ] **Wet modes**: `added_mass.rayleigh_ratios` implementation
- [ ] **Kinematic band**: Dynamic forbidden band `Z_guidevanes · n`

## Implementation Notes

### File Changes

| File | Change | Status |
|------|--------|--------|
| `turbine_runner/config.py` | Added `DEConfig` dataclass | ✅ |
| `turbine_runner/optimize.py` | `_run_dtoo()` and `_run_fenicsx()` now accept `worker_id` | ✅ |
| `turbine_runner/optimize_de.py` | **NEW** — DE driver with parallel evaluation | ✅ |
| `cluster/submit.sh` | Production SLURM script for DE (cpu, 20 tasks, 8h) | ✅ |
| `cluster/submit_dev.sh` | **NEW** — Smoke test script (dev_cpu, 4 tasks, 30min) | ✅ |

### DE Parameters (Configurable via Env)

```bash
DE_POP_SIZE=20          # Match worker count
DE_MUTATION=0.8         # F parameter
DE_CROSSOVER=0.9        # CR parameter
DE_MAX_GEN=30           # Generations (600 evals total)
DE_TOL=0.01             # Convergence tolerance
DE_SEED=42              # Optional: reproducible runs
```

### Worker Isolation

Each worker gets `$TMPDIR/worker_{id}/`:
- `design.json` — design parameters for dtOO
- `runner.msh` — generated mesh (read by FEniCSx)

FEniCSx container mounts worker dir as `/worker_data`:
```bash
enroot start -m $REPO:/workspace -m $wdir:/worker_data ...
python3 /workspace/turbine_runner/evaluate.py /worker_data/runner.msh
```

### CFD Worker Isolation

If `CFD_CASE_DIR` is set, each worker looks for case dir at:
```
$CFD_CASE_DIR/worker_{id}/
```

This requires copying/decomposing the OpenFOAM case per worker before optimization starts.

### Known Risks & Mitigations

1. **Enroot + spawn**: ✅ Mitigated — `ProcessPoolExecutor(mp_context="spawn")` starts fresh Python interpreter. Each worker calls `enroot start` independently.
2. **$TMPDIR size**: ✅ Safe — 20 workers × ~100 MB × 30 gen = ~60 GB. Node NVMe = 3.84 TB.
3. **Walltime**: ✅ Estimated 7.5h for 600 evals at 15 min each on 20 cores. Script requests 8h.
4. **CFD case collisions**: ✅ Mitigated — each worker uses `worker_{id}` subdir in `CFD_CASE_DIR`.
5. **Pickling**: ✅ Mitigated — configs converted to dicts before passing to workers. Worker function defined at module level.

## Next Steps

1. **Smoke test** on dev_cpu: `sbatch cluster/submit_dev.sh`
2. If smoke passes: **Production run** on cpu: `sbatch cluster/submit.sh`
3. If production passes: Consider enabling CFD (`CFD_CASE_DIR=/path/to/case`)
4. Monitor `turbine_runner/optimize_de.log` and `output/optimization_de.json`

## Agent Entry Points

If resuming this session, read in this order:
1. `PROGRESS.md` (this file)
2. `/tmp/opencode/handoff_2026-07-01_de-parallelization.md` (full context)
3. `turbine_runner/optimize_de.py` (main DE driver)
4. `turbine_runner/optimize.py` (modified worker functions)
5. `turbine_runner/config.py` (DE config)
6. `cluster/submit.sh` / `cluster/submit_dev.sh` (SLURM scripts)
