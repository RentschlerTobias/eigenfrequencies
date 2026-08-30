# Cluster Deployment — bwUniCluster 3.0

The optimization runs on a single node: `hydroflow-opt` drives the search on the
host, and every candidate is evaluated inside containers — dtOO + OpenFOAM for
geometry and CFD, FEniCSx for the modal solve. This document covers submitting
those runs and reading their results.

> The older Differential-Evolution path (`submit_de_*.sh`, `run_de.sh`, Pyro5
> workers, `de_state_*.json`) is still in `cluster/` but is **not** what the
> three comparison runs use. It predates hydroflow-opt and keeps no per-candidate
> isolation, which is what let a stale OpenFOAM case freeze the CFD objective
> across two runs. Prefer the path below.

## Two containers, no host environment

Both are imported straight from Docker Hub — nothing is built, pushed or
copied:

```bash
mkdir -p ~/enroot-images && cd ~/enroot-images
enroot import -o dtOO-opensuse.sqsh docker://atismer/dtoo-opensuse:stable
enroot import -o dolfinx.sqsh       docker://dolfinx/dolfinx:stable
python3 -m pip install --target ~/pylibs gmsh    # 17 MB, on a login node
```

The stock dolfinx image has no `gmsh`, and without it the modal stage cannot
read a mesh. That is what `~/pylibs` is for: the configs name it under
`[case.options.modal] pythonpath`, it gets mounted automatically, and it is
**appended** to `PYTHONPATH` rather than assigned — the image keeps its own
dolfinx on that variable, so overwriting it breaks `import dolfinx` inside an
image that plainly has it. Verified to return frequencies identical to a
custom-built image.

A self-contained image is still available via `docker/fenicsx.Dockerfile` and
`cluster/export_fenicsx_enroot.sh`, at the cost of moving 1.6 GB.

Import instructions, smoke tests and the driving venv:
`cluster/enroot_dtoo_import.md` and `cluster/enroot_fenicsx_import.md`. Run both
smoke tests before queueing anything long — the FEniCSx one solves rather than
only importing.

`source ~/pe` is no longer needed. Everything dtOO touches happens inside its
container, which sources `/usr/lib/openfoam/openfoam2606/etc/bashrc` **and**
`/dtOO-install/bin/env.sh` itself; the SWIG bindings fail to load without both.

## Submitting a run

```bash
sbatch cluster/submit_hydroflow_opt.sh cluster/configs/tistos-cfd-only.toml
```

`cluster/submit_hydroflow_opt.sh` does three things before spending the
allocation:

1. **Checks the resources against reality.** hydroflow-opt validates
   `concurrent × ranks × threads ≤ available_cpus` when it loads the config, but
   it cannot know what SLURM granted. A config claiming 40 cores in a 20-core
   allocation would pass its check and then oversubscribe the node. This exits 1
   instead.
2. **Moves scratch to `$TMPDIR`.** One candidate leaves a 21 MB mesh and a
   decomposed OpenFOAM case behind. The run directory is pinned to an absolute
   path first — hydroflow-opt resolves relative paths against the config file,
   so a config copied to `$TMPDIR` would take the results with it onto a disk
   that is wiped at job end.
3. **Warns on the memory budget.** ~10 GB per modal solve, measured on the
   tistos matrix at P2 (see below).

`DRY_RUN=1` stops after validation — resources, config, case discovery and
scratch layout all checked, nothing evaluated. Worth doing once on a login node.

## The three runs

`cluster/configs/` holds one config per run; they differ in **exactly one
line**, `eval_mode`. Population, generations, islands and seed are identical so
the runs stay comparable candidate by candidate. See
`cluster/configs/README.md`.

**Order matters: `cfd_only` first.** It is the cheapest — no modal solve — and
it is the one that proves the CFD objective varies at all.

## Sizing a run

| Quantity | Value | Source |
|---|---|---|
| tistos at P2 | 545 247 DOFs | 181 749 nodes × 3 |
| Modal solve, per candidate | ~10 GB | MUMPS INFOG(22) = 10 169 MB, measured |
| Three concurrent | ~30 GB of 96 | — |

Memory does not bind on a 256 GiB node; the cores do. `cpu_il` and `dev_cpu_il`
are Intel Xeon Platinum 8358, **64 cores, 256 GiB**, 1.8 TB local NVMe. The
modal configs run eight concurrent evaluations with eight threads each — 64
cores, ~80 GB. More concurrency means fewer threads each, not more memory.

Reproduce or re-measure for another mesh with:

```bash
python3 cluster/measure_modal_memory.py --mumps <mesh.msh> --machine tistos --no-limit
```

It asks MUMPS what the factorization costs rather than extrapolating peak RSS
from small problems, which understates the requirement — see
`.omo/evidence/task-modal-memory.md` and `docs/solver_backends.md`.

## After a run

```bash
python3 cluster/summarize_run.py runs/tistos-cfd-only
```

Exit code 0 means every metric varied and nothing failed. A metric reported as
`FROZEN` took **one** value across every candidate: that is not convergence, it
is the failure that invalidated runs 6039132/6039133. `Q` is deliberately not
checked — it comes from the mapped inlet profile and is an input, not a result.

## Run layout

```
<run_dir>/
├── config.toml            # copy of the effective input
├── manifest.json          # parameter space, provenance, evaluation ids
├── summary.json           # {total, succeeded, failed}
├── results.jsonl          # one result per line — what summarize_run.py reads
├── evaluations/<candidate_id>/
│   ├── request.json  result.json  outcome.json
│   └── stdout.log  stderr.log
└── optimization/
    ├── checkpoint.json    # written after init and after each generation
    ├── history.jsonl      # one line per generation
    └── champions.json  final-populations.json
```

Resume an interrupted run with `hydroflow-opt resume <run_dir>`.

## Provenance

Every result carries a provenance block: git commit, config hash, UTC timestamp
and the versions of dolfinx, PETSc and SLEPc where available. The element degree
that actually ran is in the result metadata and in the solver log — P1
overestimates bending-dominated frequencies by 15–20 %, so it is worth checking
that a run used what it meant to.

## Partition reference

| Partition | Nodes | Cores/Node | RAM/Node | Max time | Use case |
|---|---|---|---|---|---|
| `dev_cpu_il` | 8 | 64 | 256 GiB | 30 min | Smoke tests |
| `cpu_il` | 272 | 64 | 256 GiB | 72 h | Production |
| `highmem` | 5 | 96 | 2304 GiB | 72 h | Large P2 solves |

[USER] Verify against `sinfo -o "%P %c %m %l"` — the `#SBATCH` lines in
`submit_hydroflow_opt.sh` are written for a 40-core / 96 GB node and must match
the partition you use.
