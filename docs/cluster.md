# Cluster Deployment — bwUniCluster 3.0

Eigenfrequencies runs on bwUniCluster 3.0 using two disjoint software stacks: dtOO + OpenFOAM for geometry and CFD, and FEniCSx (inside an enroot container) for the modal solve. This document covers the practical details of submitting jobs, managing containers, and understanding provenance.

## Two stacks on the cluster

| Stack | Provider | How it is accessed |
|-------|----------|-------------------|
| dtOO + OpenFOAM | `source ~/pe` | Host environment (module `py313-dtoo`) |
| FEniCSx / dolfinx | `pyxis_fenicsx` | enroot container from `docker://dolfinx/dolfinx:stable` |

They do not live in one environment. The DE orchestrator spawns dtOO/OpenFOAM work on the host and FEniCSx work inside the container.

## Enroot / Pyxis container

The `pyxis_fenicsx` container is pre-imported on the cluster from the official `dolfinx/dolfinx:stable` Docker image. You do not build it yourself.

Quick sanity check:

```bash
enroot start -m "$PWD:/workspace" pyxis_fenicsx \
    bash -c 'python3 -c "import dolfinx; print(dolfinx.__version__)"'
```

For clusters without enroot/Pyxis, an Apptainer definition is kept at `cluster/apptainer_fenicsx.def`. Build it on a machine with `apptainer` + `fakeroot`:

```bash
apptainer build eigenfrequencies-fenicsx.sif cluster/apptainer_fenicsx.def
```

## `source ~/pe` for dtOO

Every sbatch script that touches dtOO or OpenFOAM must source the vendor environment:

```bash
source ~/pe
```

This sets `pyDtOO`, `dtOOPythonSWIG`, `simpleFoam`, and related paths. It also exports:

```bash
export OSLO_LOCK_PATH=/tmp
export FOAM_SIGFPE=0
```

## sbatch scripts

Three production sbatch wrappers live under `cluster/`. All source `cluster/_submit_de_common.sh` for the shared body.

| Script | Purpose | Default partition | Default nodes × tasks |
|--------|---------|-------------------|----------------------|
| `submit_de_cfd_only.sh` | CFD objective only (`EVAL_MODE=cfd_only`) | `cpu_il` | 4 × 4 |
| `submit_de_combined.sh` | CFD + resonance penalty (`EVAL_MODE=combined`) | `cpu_il` | 4 × 4 |
| `submit_de.sh` | Legacy wrapper (`EVAL_MODE=combined`, `RUN_TAG=legacy`) | `dev_cpu_il` | 8 × 32 |

### Example: smoke test

```bash
sbatch --partition=dev_cpu_il --nodes=6 --time=00:30:00 \
       --export=ALL,DE_MAX_GEN=1 cluster/submit_de_cfd_only.sh
```

### Example: production run with resume

```bash
sbatch --partition=cpu_il --nodes=4 --ntasks-per-node=4 --cpus-per-task=16 \
       --time=08:00:00 \
       --export=ALL,DE_POP_SIZE=16,DE_MAX_GEN=20,DE_STATE_FILE=turbine_runner/de_state_cfd_only.json \
       cluster/submit_de_cfd_only.sh
```

### Partition reference

| Partition | Nodes | Cores/Node | RAM/Node | Max time | Use case |
|-----------|-------|------------|----------|----------|----------|
| `dev_cpu_il` | 8 | 64 | 256 GiB | 30 min | Smoke tests |
| `cpu_il` | 272 | 64 | 256 GiB | 72 h | Production |
| `highmem` | 5 | 96 | 2304 GiB | 72 h | Large P2 solves |

## Islands and parallelism

In the DE (Differential Evolution) context:

- **Islands** = diversity, not parallelism. Each island evolves its own population. Island migration is planned but not yet implemented.
- **Evaluator parallelism** maps to `SLURM_NTASKS`. Each worker runs one design evaluation independently. The population size should match the total task count for best throughput.

The CLI accepts `--islands` and `--workers`, but `islands > 1` is not yet supported:

```bash
eigenfrequencies optimize --config my.yaml --optimizer de --islands 1 --workers 8
```

## Provenance

Every run writes provenance metadata into the result JSON. The provenance block includes:

- Git commit hash
- Config file hash
- Timestamp (UTC)
- Software versions (dolfinx, PETSc, SLEPc where available)

This makes every optimization result reproducible. When resuming from a checkpoint (`DE_STATE_FILE`), the provenance of the original run is preserved in the history file.

## File layout on the cluster

```
$REPO_ROOT/
├── cluster/
│   ├── _submit_de_common.sh      # shared body (sourced, not submitted)
│   ├── submit_de_cfd_only.sh    # CFD-only variant
│   ├── submit_de_combined.sh    # combined variant
│   ├── submit_de.sh             # legacy wrapper
│   ├── run_de.sh                # single-node dev runner
│   └── apptainer_fenicsx.def    # fallback Singularity image
├── server_logs/
│   └── <RUN_TAG>/               # per-variant logs and worker URIs
├── turbine_runner/
│   ├── de_state_<RUN_TAG>.json  # checkpoint
│   └── de_history_<RUN_TAG>.jsonl  # generation history
└── data/                        # copied to $TMPDIR per node at start
```
