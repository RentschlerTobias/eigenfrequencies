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
     Worker registriert sind (Default 600 s, Fortschritts-Logs alle 15 s).
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

### Quickstart (multi-node)

```
sbatch cluster/submit_de_cfd_only.sh      # EVAL_MODE=cfd_only  (reine CFD-Objective)
sbatch cluster/submit_de_combined.sh      # EVAL_MODE=combined  (CFD + Resonanz-Penalty)
```

`submit_de_cfd_only.sh` ist Smoke-konfiguriert (dev_cpu_il, 8 Nodes × 4 Tasks × 16 CPUs,
30 min, POP_SIZE=32, MAX_GEN=1) — Pipeline-Check. `submit_de_combined.sh` ist
Produktions-konfiguriert (cpu_il, 16 Nodes × 4 Tasks × 16 CPUs, 8h, POP_SIZE=64,
MAX_GEN=50, ~4-5h Laufzeit). Gemeinsamer Job-Body liegt in
`cluster/_submit_de_common.sh`; `cluster/submit_de.sh` bleibt als Legacy-Wrapper
(`RUN_TAG=legacy`, EVAL_MODE=combined) erhalten.

Smoke-Override für Combined:
```
sbatch --partition=dev_cpu_il --nodes=8 --time=00:30:00 \
       --export=ALL,DE_MAX_GEN=1 cluster/submit_de_combined.sh
```

### EVAL_MODE (Objective-Auswahl)

`turbine_runner/config.py:ObjectiveConfig.eval_mode` steuert, was pro Design
evaluiert wird (Env-Override `EVAL_MODE`):

| Wert | dtoo-Build | FEniCSx modal | CFD (simpleFoam) | Objective |
|------|-----------|---------------|------------------|-----------|
| `cfd_only` | nein | nein | ja | `cfd_scalar` |
| `resonance_only` | ja | ja | nein | `resonance_term` |
| `combined` (Default) | ja | ja | ja | `combined_objective` |

`CFD_ENABLED=0` erzwingt legacy-kompatibel das resonance_only-Verhalten.

### DESIGN_PRESET (Design-Vektor)

`turbine_runner/config.py:DesignConfig` wählt den Design-Vektor via Env
`DESIGN_PRESET`:

| Preset | DoF | Inhalt |
|--------|-----|--------|
| `full30` (Default) | 30 | Klassisches Runner-Set: {alpha_1, alpha_2, M_ex, offsetM, offsetPhiR, ratio, bladeLength, t_le/mid/te_a} × Schnitte {hub 0.0, mid 0.5, shroud 1.0}; Bounds aus `templateState.xml` Slider-Ranges |
| `t_midspan3` | 3 | Dicke LE/mid/TE nur mittschiffs (`cV_ru_t_{le,mid,te}_a_0.5`) |

Preset-Wechsel invalidiert vorhandene Checkpoints (Labels-Guard in
`optimize_de.py` → Frischstart). Bei 30 DoF `DE_POP_SIZE` ~300 und deutlich
mehr Generationen einplanen.

### Pro-Variante Namespacing (parallele Runs)

`RUN_TAG` (Wrapper-Export) namenspacet alle Artefakte, damit A/B-Runs sich
nicht gegenseitig überschreiben:

- Logs/URIs: `server_logs/<RUN_TAG>/` (inkl. `uris/`)
- Checkpoint: `turbine_runner/de_state_<RUN_TAG>.json` (`DE_STATE_FILE`)
- History: `turbine_runner/de_history_<RUN_TAG>.jsonl` (`DE_HISTORY_FILE`)

`DE_STATE_FILE`/`DE_HISTORY_FILE` respektieren vorgesetzte Env-Werte — damit
kann ein Production-Run an einen älteren Checkpoint anknüpfen:

```
sbatch --partition=cpu_il --nodes=4 --ntasks-per-node=4 --cpus-per-task=16 \
       --time=08:00:00 \
       --export=ALL,DE_POP_SIZE=16,DE_MAX_GEN=20,DE_STATE_FILE=turbine_runner/de_state_cfd_only.json \
       cluster/submit_de_cfd_only.sh
```

Hinweis: dev_cpu_il ist auf 30 min begrenzt — Production-Runs auf `cpu_il`
(72 h) oder resume-basiertes Chaining über `DE_STATE_FILE`.

## Partition reference (bwUniCluster 3.0)

| Partition | Nodes | Cores/Node | RAM/Node | Time | Notes |
|-----------|-------|------------|----------|------|-------|
| `dev_cpu_il` | 8 | 64 | 256 GiB | 30 min | Smoke-Test (priority) |
| `dev_cpu` | 1 | 96 | 384 GiB | 30 min | AMD-only dev |
| `cpu_il` | 272 | 64 | 256 GiB | 72 h | Ice Lake production |
| `cpu` | 20 | 96 | 384 GiB | 72 h | AMD production |
| `highmem` | 5 | 96 | 2304 GiB | 72 h | High-RAM |

Lokale NVMe SSD auf `cpu`/`cpu_il` für `$TMPDIR` (3.84 / 1.8 TB pro Node).
