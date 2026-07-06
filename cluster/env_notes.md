# Cluster environment notes — bwUniCluster 3.0

Two software stacks cooperate per design evaluation. They **do not** live in one
environment; that is the central integration fact.

## 1. dtOO + OpenFOAM (geometrie + CFD objective)

- Bereitgestellt durch das `de_framework`-artige Env: `source ~/pe`
  (modulisiert zu `py313-dtoo` in `~/py313-dtoo/`, der einzige Python mit
  `dtOOPythonSWIG` und `pyDtOO`).
- Exports aus `de_framework start_server.sh`:
  - `export OSLO_LOCK_PATH=/tmp`
  - `export FOAM_SIGFPE=0`
- Provides: `simpleFoam`, `decomposePar`, `reconstructPar`, `checkMesh`.
- Used by: `turbine_runner/server_de.py:_run_dtoo()` (geometrisches Build pro Worker).

## 2. FEniCSx / dolfinx (modal eigenfrequency solve)

- **Auf dem Cluster aktiv via enroot/Pyxis**:
  Container `pyxis_fenicsx` (importiert aus `docker://dolfinx/dolfinx:stable`).
- `_run_fenicsx()` ruft:
  ```
  enroot start -m "$REPO:/workspace" \
      -m "$wdir:/worker_data" pyxis_fenicsx \
      bash -c 'export HOME=/tmp; export DOLFINX_CACHE_DIR=/tmp; \
               python3 /workspace/turbine_runner/evaluate.py /worker_data/runner.msh'
  ```
- Fallback für Cluster ohne enroot/Pyxis: `cluster/apptainer_fenicsx.def`
  baut ein Singularity-Image (`eigenfrequencies-fenicsx.sif`) für den modal solve.

## 3. Pyro5 (RPC distribution)

- Persistent daemon-server ohne subprocess.pipe-Deadlocks
  (enroot + ThreadPoolExecutor inkompatibel → beobachtetes Hängen).
- Schema (rl_framework/start.sh):
  1. `python3 -m Pyro5.nameserver -n $(hostname)` auf Head-Node,
  2. pro Worker (srun-step) `python3 turbine_runner/server_de.py $worker_id $ns_host`,
  3. `srun -n 1 -N 1 ...` pro Worker → SLURM verteilt über Nodes,
  4. Client (`optimize_de.py`) dispatcht designs per RPC, polled bis genug
     Worker registriert sind (Default 120 s).
- Head-Node = Worker 0 = gleichzeitiger Client-Node (SLURM_RANK_0).

## Distribution pattern (current, `rl_framework/start.sh`-derived)

Eine SLURM-Allokation; Pyro5 Name Server auf dem Head-Node; ein Pyro5-Daemon
pro `srun -n 1 -N 1`; jeder Worker ruft `_run_dtoo()` + `_run_fenicsx()` lokal
in seiner Working-Directory. `cluster/submit_de.sh` orchestriert Nodes 1..N.

### Quickstart (single-node dev)

```
salloc -p dev_cpu_il -N 1 --ntasks-per-node=8 -t 00:30:00
cd /home/st/st_us-042020/st_ac136362/eigen/eigenfrequencies
git pull
bash cluster/run_de.sh 8 2     # 8 worker, 2 generations
```

### Quickstart (multi-node smoke)

```
sbatch --partition=dev_cpu_il --nodes=2 --ntasks-per-node=8 \
       --time=00:10:00 cluster/submit_de.sh
```

For full CFD + resonance target runs, override partition/time/nodes per the
header comment in `cluster/submit_de.sh`.

## Partition reference (bwUniCluster 3.0)

| Partition | Nodes | Cores/Node | RAM/Node | Time | Notes |
|-----------|-------|------------|----------|------|-------|
| `dev_cpu_il` | 8 | 64 | 256 GiB | 30 min | Smoke-Test (priority) |
| `dev_cpu` | 1 | 96 | 384 GiB | 30 min | AMD-only dev |
| `cpu_il` | 272 | 64 | 256 GiB | 72 h | Ice Lake production |
| `cpu` | 20 | 96 | 384 GiB | 72 h | AMD production |
| `highmem` | 5 | 96 | 2304 GiB | 72 h | High-RAM |

Lokale NVMe SSD auf `cpu`/`cpu_il` für `$TMPDIR` (3.84 / 1.8 TB pro Node).
