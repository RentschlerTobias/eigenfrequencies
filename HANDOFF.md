# HANDOFF — Cluster Testing Tutorial (bwUniCluster 3.0)

Audience: **context-free agent** continuing cluster testing.

**Status:** dtOO compiles natively ✅, FEniCSx container built ✅. Next: test the pipeline.

---

## 1. Prerequisites (already done — verify)

### 1.1 SSH + GitHub
```bash
# SSH key configured for GitHub
ssh -T git@github.com
# → Hi RentschlerTobias!

# Repo cloned on workspace (NOT home)
cd /pfs/work9/workspace/scratch/st_ac136362-eigenfreq/eigenfrequencies
git log --oneline -1
# → 2c76001 cluster: adapt for bwUniCluster 3.0 native dtOO + enroot fenicsx
```

If behind, pull:
```bash
git pull origin cfd-eigenfreq-multiobjective
```

### 1.2 dtOO Environment
```bash
source ~/pe
# Loads: Python 3.13.3, OpenFOAM v2412, modules
# Sets: LD_LIBRARY_PATH for ~/dtOO/install/{lib,lib64}
```

Verify dtOO imports:
```bash
python3 -c "import dtOOPythonSWIG; print('OK')"
# → OK (with harmless Gmsh warnings)
```

### 1.3 Enroot Container (FEniCSx)
Built once in `~/.local/share/enroot/`:
```bash
enroot list
# → pyxis_fenicsx
```

Verify:
```bash
REPO=/pfs/work9/workspace/scratch/st_ac136362-eigenfreq/eigenfrequencies
enroot start -m "$REPO:/workspace" pyxis_fenicsx \
    python3 -c "import dolfinx; print(dolfinx.__version__)"
# → 0.11.0.post0
```

---

## 2. What changed in commit 2c76001

Three files adapted for cluster:

| File | Change |
|------|--------|
| `turbine_runner/dtoo_export.py` | Removed hardcoded Docker paths (`/dtOO`, `/work`). Defaults: `~/dtOO/build/test/tistos`, `data/runner.msh`. Added `DTOO_LOG_FILE` env var. |
| `turbine_runner/optimize.py` | `_run_dtoo()`: `docker run` → `bash -lc "source ~/pe && python3 dtoo_export.py"`. `_run_fenicsx()`: `docker run` → `enroot start -m $REPO:/workspace pyxis_fenicsx ...` |
| `cluster/submit.sh` | `source ~/pe` (not `~/de`), partition `dev_cpu`, 1 node, enroot `FENICSX_CONTAINER` instead of apptainer SIF. |

---

## 3. Step-by-step testing

### 3.1 Test dtOO native (interaktive Node — NOT login node)

```bash
# Request node (dev_cpu = 1 Node, 30 Min)
salloc -p dev_cpu -n 1 -t 00:30:00

# On the compute node:
cd /pfs/work9/workspace/scratch/st_ac136362-eigenfreq/eigenfrequencies/turbine_runner
source ~/pe
python3 dtoo_export.py

# Expected output:
# [dtoo] no design JSON -> building baseline (template) geometry
# [dtoo] plugin ru_adjustDomain applied
# [dtoo] makeGrid on ruWithRounding_mechMesh ...
# [dtoo] mesh written: .../data/runner.msh

# Verify:
ls -lh data/runner.msh
# → > 0 bytes

exit  # Release node
```

### 3.2 Test FEniCSx modal solve (interaktive Node)

```bash
salloc -p dev_cpu -n 1 -t 00:30:00

REPO=/pfs/work9/workspace/scratch/st_ac136362-eigenfreq/eigenfrequencies
enroot start -m "$REPO:/workspace" pyxis_fenicsx \
    python3 /workspace/turbine_runner/evaluate.py \
    /workspace/turbine_runner/data/runner.msh

# Expected output:
# [mesh_prep] read ...: topology.dim=3
# [solver] clamped facets=..., fixed DOFs=...
# [solver] system DOFs=..., free DOFs=...
# Computed Eigenfrequencies:
#   Mode 1: 18.80 Hz
#   Mode 2: 80.40 Hz
#   Mode 3: 101.10 Hz
#   ...
# RESULT_JSON {"frequencies_hz": [18.8, 80.4, ...], "ok": true}

exit
```

### 3.3 Test resonance-only optimization (interaktive Node)

```bash
salloc -p dev_cpu -n 1 -t 00:30:00

cd /pfs/work9/workspace/scratch/st_ac136362-eigenfreq/eigenfrequencies/turbine_runner
source ~/pe

# CFD disabled → only resonance penalty
CFD_CASE_DIR="" OPT_MAX_ITER=3 python3 optimize_multi.py

# Expected:
# Runner CFD + resonance multi-objective optimization
# CFD case dir  : (none -> resonance-only)
# [eval 1] objective=22.9  ...
# [eval 2] objective=...
# ...
# Best objective: ...
# History       : output/optimization_multi.json

exit
```

### 3.4 Full batch job (SLURM)

```bash
cd /pfs/work9/workspace/scratch/st_ac136362-eigenfreq/eigenfrequencies
sbatch cluster/submit.sh

# Monitor:
squeue -u $USER
# or
cat turbine_runner/optimize_multi.log
```

---

## 4. Filesystem layout on cluster

| Path | Purpose | Lifetime |
|------|---------|----------|
| `~/dtOO` | dtOO installation (binaries, libs) | Permanent |
| `~/.local/share/enroot/pyxis_fenicsx/` | FEniCSx container | Permanent |
| `/pfs/work9/...st_ac136362-eigenfreq/` | Workspace (Repo, outputs) | 60 days (renewable) |
| `$TMPDIR` | Node-local SSD (staging) | Job lifetime |

---

## 5. Gotchas

1. **Never run compute on login nodes.** Jobs > 1 min or > 8 GB will be killed without warning. Use `salloc` or `sbatch`.

2. **Repo is on workspace, not home.** The mount path for enroot must be the workspace path:
   ```bash
   REPO=/pfs/work9/workspace/scratch/st_ac136362-eigenfreq/eigenfrequencies
   # NOT ~/eigenfrequencies (symlink may not work)
   ```

3. **Enroot vs Apptainer.** bwUniCluster recommends Enroot. The container name MUST start with `pyxis_` for SLURM integration. We use `pyxis_fenicsx`.

4. **Environment file is `~/pe`, not `~/de`.** (old de_framework reference said `~/de`, actual file is `~/pe`).

5. **dtOO exports to `data/runner.msh`** (relative to `turbine_runner/`). The old Docker path `/work/runner.msh` no longer exists.

6. **CFD is optional.** If `CFD_CASE_DIR` is empty or missing, `optimize_multi.py` degrades to resonance-only. This is the correct first test.

---

## 6. Next steps after pipeline works

1. **Enable CFD:** Build OpenFOAM case from dtOO state (port `createStatesAndMeshes.CreateMeshes` from de_framework).
2. **Validate CFD columns:** Check `cfd_eval.py` indices against real `postProcessing/` output.
3. **Wet modes:** Implement `added_mass.rayleigh_ratios` (Laplace added mass) → wet frequencies.
4. **Kinematic band:** Move forbidden band from fixed [100,150] Hz to blade-passing frequency (`Z_guidevanes · n`).
5. **P2 convergence:** Test `SolverConfig.element_degree=2` on cluster nodes (more memory, more accurate).

---

## 7. Useful commands

```bash
# Check node availability
sinfo_t_idle

# Interactive node
salloc -p dev_cpu -n 1 -t 00:30:00

# Cancel job
scancel <JOBID>

# Check quotas
lfs quota -uh $(whoami) $HOME
lfs quota -uh $(whoami) /pfs/work9

# Workspace management
ws_allocate myws 60
ws_find myws
ws_list
ws_extend myws 60
```

---

## 8. References

- `documentation.md` — physics rationale, design decisions, status
- `cluster/env_notes.md` — how dtOO + OpenFOAM stack and FEniCSx stack interact
- `cluster/apptainer_fenicsx.def` — container definition (imported via enroot)
- `cluster/submit.sh` — SLURM batch script
- `turbine_runner/optimize_multi.py` — main optimization loop
- bwHPC Wiki: https://wiki.bwhpc.de/e/BwUniCluster3.0
