# Cluster environment notes — bwUniCluster 3.0

Two disjoint software stacks are needed per design evaluation. They do **not** live
in one environment; that is the central integration fact.

## 1. dtOO + OpenFOAM (geometry build + CFD objectives)

- Provided by the de_framework-style env: `source ~/de`, or a module such as
  `. dtoo of_v2406_15.6` (dtOO + OpenFOAM v2406).
- Exports needed (from de_framework `start_server.sh`):
  - `export OSLO_LOCK_PATH=/tmp`
  - `export FOAM_SIGFPE=0`
- Provides: `dtOOPythonSWIG` / `pyDtOO`, and `simpleFoam`, `decomposePar`,
  `reconstructPar`, `checkMesh`.
- Used by: `turbine_runner/dtoo_export.py` (mech mesh + OF case) and the
  `simpleFoam` run whose `postProcessing/` is read by `turbine_runner/cfd_eval.py`.

## 2. FEniCSx / dolfinx (modal eigenfrequency solve)

- **Not set up on the cluster yet** — provision via apptainer:
  `apptainer build eigenfrequencies-fenicsx.sif cluster/apptainer_fenicsx.def`,
  copy the `.sif` to the cluster, point `FENICSX_SIF` at it (see `submit.sh`).
- Used by: `turbine_runner/solver.py` + `evaluate.py` (and later `added_mass.py`).

## Wiring the modal solve through apptainer

`turbine_runner/optimize.py:_run_fenicsx()` currently calls `docker run …`. On the
cluster, replace the docker invocation with apptainer, e.g.:

```bash
apptainer exec --bind "$REPO:/workspace" "$FENICSX_SIF" \
    python3 /workspace/turbine_runner/evaluate.py \
    /workspace/turbine_runner/data/runner.msh
```

Set `FENICSX_IMAGE`/the helper accordingly, or add an `apptainer` branch keyed on
an env flag (`RUNNER_BACKEND=apptainer`). Keep the `RESULT_JSON` stdout contract.

Likewise `optimize.py:_run_dtoo()` wraps dtOO in `docker run atismer/...` — wrong on
the cluster, where dtOO is **native** (`dtOOPythonSWIG` under `source ~/de`). Run
`python3.12 dtoo_export.py` directly with `DTOO_DESIGN_JSON`, `DTOO_OUTPUT_MSH`,
`DTOO_CASE_DIR` set to the staged paths; no docker. The same `RUNNER_BACKEND` switch
should select native dtOO vs the local docker image.

## Distribution pattern (reference, de_framework `start.sh`)

One SLURM allocation; a Pyro5 nameserver (`pyro5-ns`) on the batch node; one worker
per `SLURM_NTASKS`; each design RPCs a co-located worker that runs dtOO + `mpiexec
simpleFoam -parallel` in `$TMPDIR`. `cluster/submit.sh` is the simplified single-loop
starting point; scale to the Pyro/archipelago pattern if parallel evals are needed.
