# eigenfrequencies

**Eigenfrequency-aware shape optimisation of hydraulic turbine runners.**

Adds a structural objective to [dtOO](https://github.com/ihs-ustutt/dtOO) — the IHS in-house hydraulic shape optimiser — so that runner designs can simultaneously optimise efficiency, cavitation, and head while staying clear of blade-passing resonance bands. The FEM solver, optimiser, and cluster deployment are packaged as a standalone pip-installable Python library.

> **Status** — Stage 1 complete: dry modal analysis, DE optimisation, cluster deployment.
> Stage 2 (wet added-mass / FSI) and Stage 3 (data-driven surrogates) are future work.

---

## How it works

### 1 · Modal analysis (FEniCSx + SLEPc)

The runner is treated as a linear elastic body. The weak form of the equations of motion leads to the **generalized eigenvalue problem**:

```
K · φ = λ · M · φ
```

where **K** is the stiffness matrix, **M** the mass matrix, **φ** the mode shape, and **λ = (2πf)²** gives the eigenfrequency *f* in Hz.

The package assembles K and M with [FEniCSx](https://fenicsproject.org/) using **quadratic tetrahedral elements (P2, tet10)**. A mesh with 325 k tets yields roughly **2 M degrees of freedom** — large enough to resolve the first 10–15 modes to experimental accuracy (≤ 3 %).

Two solver backends are available:

| Backend | Library | Use case |
|---|---|---|
| `scipy` | `scipy.sparse.linalg.eigsh` | Local development, small and medium problems |
| `slepc` | PETSc + SLEPc, Krylov–Schur, MUMPS | Cluster, large problems (past ~1M DOFs) |

Both support every BC mode — clamped and free-free — and agree to machine
precision on the same problem, so the choice is one of numerics, not of
physics. scipy slices the constrained DOFs out of the CSR matrices; SLEPc keeps
the sparsity and pushes them to an infinite eigenvalue by writing a unit
diagonal into K and a zero diagonal into M. The equivalence is pinned by
`tests/solver/test_backend_equivalence.py`.

```
src/eigenfrequencies/solver/
├── core.py          ← ModalSolver class (assemble → BC → solve → Hz)
├── scipy_backend.py ← sparse free-DOF restriction, ARPACK
├── slepc_backend.py ← shift-invert, Krylov-Schur
└── rayleigh.py      ← Rayleigh-quotient refinement step
```

### 2 · Penalty / resonance objective

A runner rotating at *n* RPM with *Z* guide vanes is excited at the blade-passing frequency and its harmonics:

```
f_bp(k) = k · Z · n / 60    k = 1, 2, ..., max_harmonic
```

Each harmonic defines a **forbidden band** `[f_bp(k) − margin, f_bp(k) + margin]`. The resonance penalty is a triangle function that rises from 0 at the band edge to 1 at the centre:

```
penalty(f) = max over all bands of  max(0, 1 − |f − f_bp| / margin)
```

For a combined CFD + modal objective, a hydraulic scalar term is added:

```
f_total = w_eta·tanh(|1+η|) + w_cav·tanh(V_cav·1e6) + w_head·tanh(|ΔH|)
        + w_resonance · penalty(f_modes)
```

Lower is better (minimisation).

```
src/eigenfrequencies/penalty/
├── band.py       ← compute_penalty(), band_report()
└── objective.py  ← cfd_scalar(), resonance_term(), combined_objective()
```

### 3 · Differential evolution optimiser

The optimiser asks for a population of design vectors, evaluates them in parallel via a worker pool, and tells the results back. Any gradient-free backend (DE, PSO, CMA-ES, BO) plugs in through the same `ask / tell` protocol.

```
src/eigenfrequencies/optimize/
├── protocol.py            ← Optimizer protocol (ask / tell / state_dict / load_state)
├── backends/
│   ├── de.py              ← DE/rand/1/bin (default)
│   ├── pso.py             ← Particle Swarm
│   ├── cmaes.py           ← CMA-ES (via cma package)
│   └── bo.py              ← Bayesian Optimisation (via optuna)
└── evaluators/
    ├── base.py            ← EvaluatorPool protocol
    ├── process_pool.py    ← Local multiprocessing (development)
    └── pyro_pool.py       ← Pyro5 RPC (cluster, multi-node)
```

### 4 · Machine adapters (dtOO integration)

A machine adapter connects a dtOO parametric case to the solver. It exposes:
- design-parameter bounds (`[lo, hi, x0]` per parameter)
- mesh export (`run_dtoo → runner.msh`)
- boundary-condition template (hub clamp / axial plane / free-free)

```
src/eigenfrequencies/adapters/
├── dtoo/
│   ├── adapter.py     ← DtooAdapter (export_mesh, bc, design_bounds)
│   ├── export.py      ← low-level dtOO Python binding
│   └── machine_yaml.py← YAML loader + validation
└── cluster/
    └── runner.py      ← run_dtoo() + run_fenicsx() for SLURM workers
```

### 5 · Cluster deployment (bwUniCluster 3.0)

On the cluster, dtOO runs natively (via `source ~/pe`) and FEniCSx runs inside an enroot/Pyxis container (`pyxis_fenicsx`). Workers register themselves on a shared filesystem and the coordinator discovers them via URI files — no Pyro5 name server required.

```
SLURM job
├── srun -n1  eigenfrequencies cluster worker 0 --uri-dir $URI_DIR  → worker_0.uri
├── srun -n1  eigenfrequencies cluster worker 1 --uri-dir $URI_DIR  → worker_1.uri
├── ...
└── eigenfrequencies optimize --config tistos.yaml --optimizer de \
        --evaluator pyro5 --uri-dir $URI_DIR --workers N
```

---

## Project layout

```
eigenfrequencies/
├── src/eigenfrequencies/       ← Python package
│   ├── cli.py                  ← Typer CLI entry point
│   ├── config.py               ← Dataclasses (Material, BC, Mesh, Solver, …)
│   ├── config_yaml.py          ← YAML loader → RunConfig
│   ├── solver/                 ← FEM modal solver
│   ├── penalty/                ← Resonance objective + band utilities
│   ├── optimize/               ← Backends, evaluators, island protocol
│   ├── adapters/               ← dtOO + cluster adapters
│   ├── cluster/                ← Pyro5 worker server
│   ├── io/                     ← Mesh loading, XDMF/VTK output
│   ├── materials/              ← Material presets (steel, bronze, …)
│   ├── bc/                     ← BC builder functions
│   ├── mcp/                    ← MCP server (AI agent integration)
│   └── validation/             ← Beam + Laval disc validation suites
├── examples/configs/           ← Ready-to-use YAML configs
├── adapters/machines/          ← Machine YAML files (tistos, canadaLight)
├── turbine_runner/             ← Case-specific scripts + legacy runner
├── cluster/                    ← SLURM submit scripts
├── tests/                      ← pytest suite (unit + characterisation)
└── docs/                       ← Detailed documentation
```

---

## Validation

| Test case | Reference | FEniCSx result | Agreement |
|---|---|---|---|
| Cantilever beam (1 m steel, clamped) | Euler–Bernoulli analytical | first 3 bending modes | ≤ 1 % |
| Laval bronze disc (d=200 mm, hammer impact) | Experiment + ANSYS | 1ND, 2ND, 3ND, 4ND | ≤ 3 % vs experiment |

Run the beam suite:

```bash
eigenfrequencies validate --suite beam
```

Run the Laval disc suite (requires `RUN_TESTCASE_VALIDATION=1` and the disc mesh):

```bash
RUN_TESTCASE_VALIDATION=1 eigenfrequencies validate --suite testcase
```

---

## Installation

FEniCSx is not on PyPI — it is distributed through conda-forge.

### Option A — conda + uv (recommended)

```bash
conda env create -f environment.yml
conda activate eigenfrequencies
uv pip install -e ".[optimize,mcp,dev]"
eigenfrequencies --help
```

### Option B — Docker (local development)

```bash
./scripts/build_container.sh   # builds eigenfrequencies-fenicsx:latest
./scripts/run_container.sh     # /workspace is the repo root
```

### Option C — bwUniCluster 3.0 (enroot)

```bash
source ~/pe                    # dtOO + OpenFOAM
enroot start -m "$PWD:/workspace" pyxis_fenicsx \
    bash -c 'python3 -c "import dolfinx; print(dolfinx.__version__)"'
```

Full details: [`docs/install.md`](docs/install.md)

---

## Tutorial

### Step 1 — Solve a modal problem

Create a YAML config (or use `examples/configs/beam.yaml`):

```yaml
# my_runner.yaml
material:
  youngs_modulus: 210.0e9
  density: 7850.0
  poisson_ratio: 0.30

bc:
  mode: axial_plane
  axis: z
  plane_value: 0.0
  plane_tol: 1.0e-6

mesh:
  msh_path: data/runner.msh

solver:
  num_eigenvalues: 10
  element_degree: 2
  solver_backend: scipy

output:
  output_dir: output/my_runner
```

Run the solve:

```bash
eigenfrequencies solve --config my_runner.yaml
```

Output:

```
Frequencies (Hz):
  Mode 1: 312.41 Hz
  Mode 2: 312.43 Hz
  Mode 3: 498.77 Hz
  ...
```

Results are written to `output/my_runner/frequencies.json` with full provenance metadata (git hash, config hash, timestamp).

### Step 2 — Discover mesh axis and calibrate scale

dtOO meshes are sometimes in scaled or rotated coordinates. Use the axis-discovery diagnostic:

```bash
eigenfrequencies dtoo discover-axis --mesh data/runner.msh
```

Output:

```
rotation_axis: z
confidence: 18.4231
axis_details:
  x: min=-0.2146  max=+0.2146  span=0.4292
  y: min=-0.2146  max=+0.2146  span=0.4292
  z: min=+0.0000  max=+0.2641  span=0.2641  <-- rotation_axis
```

If the mesh is in non-physical units, measure the scale factor from a known feature:

```bash
eigenfrequencies dtoo measure-scale \
    --mesh data/runner.msh \
    --physical-length 0.264 \
    --feature-desc "runner height"
```

Paste the `mesh_scale_factor` snippet into your machine YAML.

### Step 3 — Run design optimisation (local)

Add a `design` block and `de` block to your config:

```yaml
# in my_runner.yaml
design:
  params:
    cV_ru_bladeLength_0.5: [0.60, 1.00, 0.80]  # [min, max, x0]
    cV_ru_bladeLength_1.0: [0.80, 1.30, 1.05]

de:
  pop_size: 16
  mutation: 0.8
  crossover: 0.9
  max_generations: 50
  seed: 42

optimization:
  n_rpm: 90.0
  Z_guidevanes: 18
  max_harmonic: 5
  margin_hz: 5.0

objective:
  mode: penalty
  w_resonance: 1.0
```

Start optimisation with 4 local workers:

```bash
eigenfrequencies optimize \
    --config my_runner.yaml \
    --optimizer de \
    --evaluator process_pool \
    --workers 4
```

Progress per generation:

```
[gen 0] best=3.214100  mean=8.471233
[gen 1] best=2.980312  mean=6.223144
...
```

Resume from checkpoint if interrupted:

```bash
eigenfrequencies optimize \
    --config my_runner.yaml \
    --optimizer de \
    --workers 4 \
    --resume output/de_state.json
```

Print a summary of the finished run:

```bash
eigenfrequencies report --run-dir output/my_runner
```

### Step 4 — Run on the cluster (bwUniCluster 3.0)

Copy the repository to the cluster scratch filesystem, then submit:

```bash
# Quick smoke test (dev partition, 2 nodes × 4 tasks, 30 min)
EVAL_MODE=resonance_only sbatch cluster/submit_eigenfreq.sh

# Production run
EVAL_MODE=resonance_only \
OPTIMIZER=de \
N_NODES=4 \
N_TASKS_NODE=8 \
PARTITION=cpu_il \
WALLTIME=08:00:00 \
sbatch cluster/submit_eigenfreq.sh
```

The submit script automatically starts one Pyro5 worker per SLURM task, waits for all URI files to appear on the shared filesystem, then launches the coordinator.

Manual multi-node workflow (for debugging):

```bash
# Terminal 1 (one per worker, replace N with task id):
DE_URI_DIR=/pfs/work9/.../uris eigenfrequencies cluster worker 0 --uri-dir $DE_URI_DIR &

# Terminal 2 (coordinator):
eigenfrequencies optimize \
    --config adapters/machines/tistos.yaml \
    --optimizer de \
    --evaluator pyro5 \
    --uri-dir /pfs/work9/.../uris \
    --workers 8
```

Full cluster guide: [`docs/cluster.md`](docs/cluster.md)

---

## CLI reference

```
eigenfrequencies [OPTIONS] COMMAND [ARGS]...

Commands:
  solve          Run modal analysis from a YAML config
  validate       Run validation suite (beam | testcase)
  optimize       Run design optimisation
  report         Print summary from an optimisation run
  rl-export      Export DE history to offline RL dataset (d3rlpy)
  dtoo           dtOO mesh helper utilities
    discover-axis  Detect rotation axis from mesh bounding box
    measure-scale  Compute mesh_scale_factor from a known feature size
  cluster        Cluster worker utilities
    worker         Start a Pyro5 evaluation worker (one per SLURM task)
```

### `solve`

```bash
eigenfrequencies solve \
    --config examples/configs/beam.yaml \
    [--mesh data/runner.msh] \
    [--out output/myrun] \
    [--json]
```

Writes `output_dir/frequencies.json` with eigenfrequencies, eigenvalues, and provenance.

### `validate`

```bash
eigenfrequencies validate --suite beam
eigenfrequencies validate --suite testcase
RUN_TESTCASE_VALIDATION=1 eigenfrequencies validate --suite testcase --full
```

Exits with code 0 on pass, 4 on failure (> 5 % deviation).

### `optimize`

```bash
eigenfrequencies optimize \
    --config examples/configs/tistos.yaml \
    --optimizer de \
    [--islands 1] \
    [--workers 8] \
    [--evaluator process_pool|pyro5] \
    [--uri-dir /path/to/uris] \
    [--resume output/de_state.json] \
    [--budget 400] \
    [--out output/myrun]
```

| `--optimizer` | Notes |
|---|---|
| `de` | Differential evolution DE/rand/1/bin (default) |
| `pso` | Particle swarm |
| `cmaes` | CMA-ES via `cma` package |
| `bo` | Bayesian optimisation via `optuna` |

| `--evaluator` | Notes |
|---|---|
| `process_pool` | Local `multiprocessing.Pool` (development/CI) |
| `pyro5` | Pyro5 RPC workers on shared filesystem (cluster) |

### `cluster worker`

```bash
eigenfrequencies cluster worker <id> \
    --uri-dir /pfs/work9/.../uris \
    [--config adapters/machines/tistos.yaml]
```

Starts a Pyro5 daemon on the local node, writes its URI to `uri_dir/worker_<id>.uri`, and blocks until SLURM kills the job.

---

## Configuration reference

All commands accept a YAML file that maps to `RunConfig`. The full schema is at [`schema/run_config.json`](schema/run_config.json).

### Key sections

```yaml
material:
  youngs_modulus: 210.0e9   # Pa
  density:        7850.0    # kg/m³
  poisson_ratio:  0.30

bc:
  mode:        axial_plane  # radius_band | axial_plane | free
  axis:        z            # x | y | z  (rotation axis)
  plane_value: 0.0          # coordinate of the clamped face
  plane_tol:   1.0e-6
  # For radius_band:
  # hub_center: [0.0, 0.0]
  # hub_radius: 0.15

mesh:
  msh_path:             data/runner.msh
  mesh_scale_factor:    1.0   # multiply coordinates to recover metres

solver:
  num_eigenvalues:  10
  element_degree:   2         # 1=P1 (fast), 2=P2 (accurate)
  solver_backend:   scipy     # scipy | slepc
  tolerance:        1.0e-6

optimization:
  n_rpm:          90.0
  Z_guidevanes:   18
  max_harmonic:   5
  margin_hz:      5.0        # half-width of forbidden bands in Hz
  margin_fraction: 0.05      # alternative: relative margin

design:
  params:
    my_param: [lo, hi, x0]   # [min, max, initial value]

de:
  pop_size:        16
  mutation:        0.8
  crossover:       0.9
  max_generations: 50
  seed:            42

objective:
  mode:         penalty      # penalty | hard
  w_resonance:  1.0
  hard_penalty: 1.0e6        # used when mode=hard

output:
  output_dir:  output
  save_xdmf:   true          # write mode shapes to output/*.xdmf
```

---

## Python API

The CLI wraps a clean Python API. Use it directly in scripts or notebooks:

```python
from pathlib import Path
from eigenfrequencies.config_yaml import load_config
from eigenfrequencies.io import load_and_prepare_mesh
from eigenfrequencies.solver import ModalSolver

run_cfg = load_config(Path("examples/configs/beam.yaml"))
domain  = load_and_prepare_mesh(run_cfg.mesh)
solver  = ModalSolver(domain, run_cfg.material, run_cfg.bc, run_cfg.solver)

eigenvalues, eigenvectors = solver.solve()
frequencies = solver.compute_frequencies(eigenvalues)

for i, f in enumerate(frequencies):
    print(f"Mode {i+1}: {f:.2f} Hz")
```

Compute the resonance penalty for a set of frequencies:

```python
from eigenfrequencies.penalty.band import compute_penalty, band_report
from eigenfrequencies.config import OptimizationConfig

opt_cfg = OptimizationConfig(n_rpm=90.0, Z_guidevanes=18, max_harmonic=5)
penalty = compute_penalty(frequencies, opt_cfg)
report  = band_report(frequencies, opt_cfg)
print(f"Penalty: {penalty:.4f}")
```

---

## Machine adapters

Adapters are YAML files under `adapters/machines/`. They define:
- `case_dir` — dtOO case directory (with `machine.xml`)
- `state` — dtOO state to load
- `design` — parameter bounds `{label: {min, max}}`
- `bc_template` — boundary-condition template
- `mesh_scale_factor` — coordinate scaling to SI metres

Shipped adapters:

| Adapter | Machine | DOFs | BC |
|---|---|---|---|
| `tistos.yaml` | Tistos Francis runner | 30 | hub clamp at `z=0` |
| `canadaLight.yaml` | Laval full turbine | 21 | free-free |

Load an adapter in Python:

```python
from eigenfrequencies.adapters.dtoo.adapter import DtooAdapter

adapter   = DtooAdapter("adapters/machines/tistos.yaml")
mesh_path = adapter.export_mesh({"cV_ru_bladeLength_0.5": 0.75})
bc_cfg    = adapter.bc()
bounds    = adapter.design_bounds()   # list of (lo, hi) per parameter
```

Full adapter guide: [`docs/adapters.md`](docs/adapters.md)

---

## MCP server (AI assistant integration)

An MCP server exposes `solve_modal`, `optimize_start`, `job_status`, and `fetch_results` as async tools that AI coding assistants (Claude, OpenCode) can call:

```bash
eigenfrequencies-mcp
```

Add to `.opencode/mcp.json` or `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "eigenfrequencies": {
      "command": "eigenfrequencies-mcp",
      "env": { "EIGENFREQ_JOBS_ROOT": ".eigenfrequencies/jobs" }
    }
  }
}
```

Full MCP guide: [`docs/mcp.md`](docs/mcp.md)

---

## Documentation & Slides

The Sphinx documentation and the *Eigenfrequency-Aware CFD Optimization* Quarto/reveal.js slide deck are published together on GitHub Pages.

- **Sphinx docs:** quickstart, theory, API reference.
- **Slides:** `docs/slides/slides.qmd` (rendered with `quarto render --to revealjs`), based at `docs/slides/`. The deck covers the full freq-aware CFD optimisation pipeline presented in the Stuttgart–Laval project exchange.

To enable Pages on a fresh clone:

1. Push the repo to GitHub (or use the existing `RentschlerTobias/eigenfrequencies` remote).
2. In **Settings → Pages → Build and deployment → Source**, select **GitHub Actions**.
3. The `docs` job in `.github/workflows/ci.yml` builds Sphinx + Quarto and deploys automatically on every push to `main`.

To render the slides locally:

```bash
# Install Quarto CLI from https://quarto.org/
quarto render docs/slides --to revealjs
# Open docs/slides/slides.html in a browser
```

---

## License

MIT — IHS University of Stuttgart.
