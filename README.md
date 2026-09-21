# eigenfrequencies

**Modal analysis and resonance penalty for hydraulic machine components.**

Given the structural-mechanics mesh (`.msh`, typically exported by
[dtOO](https://github.com/ihs-ustutt/dtOO)) of a runner, this package computes its
**eigenfrequencies** and a **raw resonance penalty** that measures how close the modes sit to the
blade-passing excitation bands.

---

## Install

FEniCSx (`dolfinx`) is not distributed on PyPI — install it via conda-forge.

```bash
conda env create -f environment.yml
conda activate eigenfrequencies
pip install -e ".[dev]"
```

Runtime dependencies are only `numpy` and `pyyaml`; the FEM solver requires `dolfinx`. Python
`>=3.11,<3.14`.

---

## Quick start

### Python API

```python
from eigenfrequencies import load_preset, solve_modal

config = load_preset("tistos", {"n_rpm": 72.0})      # machine preset + overrides
result = solve_modal("ruWithRounding_mechMesh.msh", config)

print(result.frequencies_hz)      # (312.41, 312.43, 498.77, ...)  tuple of Hz
print(result.resonance_penalty)   # raw, unweighted float
print(result.violating_modes)     # 1-based mode indices inside a forbidden band
print(result.band_report)         # human-readable band summary
```

Need only the scalar? Use the thin wrapper:

```python
from eigenfrequencies import load_preset, solve_modal_penalty

penalty = solve_modal_penalty("mech.msh", load_preset("tistos", {"n_rpm": 72.0}))
```

### Command line

```bash
# machine preset + overrides
eigenfrequencies --msh mech.msh --machine tistos --n-rpm 72 --stdout

# full YAML config
python -m eigenfrequencies.solve --msh mech.msh --config run.yaml --result out.json
```

| Option | Meaning |
|---|---|
| `--msh` | structural-mechanics `.msh` (required) |
| `--config` | full `ModalAnalysisConfig` YAML |
| `--machine` | machine preset name (e.g. `tistos`) |
| `--n-rpm` | rotational speed (required with `--machine`) |
| `--set KEY=VALUE` | extra resonance override (repeatable) |
| `--result` | write the JSON result to this path |
| `--stdout` | print the JSON result to stdout |

The JSON result contains `frequencies_hz`, `resonance_penalty`, `violating_modes`, `band_report`
and `metadata`.

---

## How it works

### 1 · Modal analysis (FEniCSx)

The runner is treated as a linear elastic body. The weak form of the equations of motion yields the
**generalized eigenvalue problem**

```
K · φ = λ · M · φ
```

with stiffness **K**, mass **M**, mode shape **φ** and **λ = (2πf)²**. The package assembles K and M
with [FEniCSx](https://fenicsproject.org/) (P1 or P2 tetrahedra) and solves for the lowest
`num_eigenvalues` modes.

Two backends are available and agree to machine precision on the same problem:

| Backend | Library | Use case |
|---|---|---|
| `scipy` | `scipy.sparse.linalg.eigsh` | local development, small/medium problems |
| `slepc` | PETSc + SLEPc, Krylov–Schur | cluster, large problems (past ~1M DOFs) |

```
src/eigenfrequencies/solver/
├── core.py          ← ModalSolver (assemble → BC → solve → Hz)
├── scipy_backend.py ← sparse free-DOF restriction, ARPACK
├── slepc_backend.py ← shift-invert, Krylov–Schur
└── rayleigh.py      ← Rayleigh-quotient refinement
```

Backend details: [`docs/solver_backends.md`](docs/solver_backends.md)

### 2 · Resonance penalty (raw)

A runner rotating at *n* RPM with *Z* guide vanes is excited at the blade-passing frequency and its
harmonics:

```
f_bp(k) = k · Z · n_rpm / 60        k = 1, 2, …, max_harmonic
```

Each harmonic defines a **forbidden band** `[center − margin, center + margin]` with
`margin = max(margin_hz, center · margin_fraction)`. Every eigenfrequency that falls inside a band
contributes its distance to the nearer band edge, in Hz:

```
penalty = penalty_k · Σ_modes  min(f − lo, hi − f)      (0 when no mode is inside a band)
```

Lower is better. The returned value is **raw** (`penalty_k = 1.0`): the caller is expected to scale
it and combine it with the CFD objective — this repo does not weight or combine anything.

```
src/eigenfrequencies/penalty/
└── band.py       ← compute_penalty(), band_report(), violating_modes()
```

### 3 · Added mass (optional)

`added_mass/` provides the dry→wet frequency shift from added-mass ratios
(`wet_from_ratios`, `placeholder_ratios`); the Rayleigh-based variant is a stub.

---

## Configuration

All settings live in the frozen dataclass `ModalAnalysisConfig`, with the sections `material`,
`bc`, `mesh`, `solver`, `resonance`, `wet_mode`, `output`. The machine-readable schema is
[`schema/eigenfrequencies-config.schema.json`](schema/eigenfrequencies-config.schema.json).

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
  # for radius_band:
  # hub_center: [0.0, 0.0]
  # hub_radius: 0.15

mesh:
  msh_path:            data/runner.msh
  scale_factor:        1.0   # multiply coordinates to recover metres

solver:
  num_eigenvalues:  10
  element_degree:   2         # 1 = P1 (fast), 2 = P2 (accurate)
  solver_backend:   scipy     # scipy | slepc
  tolerance:        1.0e-6

resonance:
  n_rpm:           72.0
  Z_guidevanes:    18
  max_harmonic:    6
  margin_hz:       5.0        # minimum half-width of a band, in Hz
  margin_fraction: 0.05       # relative alternative, fraction of the band centre
  penalty_k:       1.0        # kept at 1.0 for a raw penalty

output:
  output_dir:  output
  save_xdmf:   true
```

Load and dump it programmatically:

```python
from eigenfrequencies.config_yaml import load_config, dump_config

config = load_config("run.yaml")     # -> ModalAnalysisConfig, strict key validation
dump_config(config, "run_copy.yaml")
```

---

## Machine presets

Presets are YAML files under `adapters/machines/`. They carry only modal-physics defaults — no
design space and no dtOO case paths (those belong to the calling optimiser):

```yaml
name: tistos
material:      { youngs_modulus: 210.0e9, density: 7850.0, poisson_ratio: 0.30 }
solver:        { num_eigenvalues: 10, element_degree: 2, solver_backend: scipy }
bc_template:   { type: hub_clamp, params: { hub_center: [0.0, 0.0], hub_radius: 0.15 } }
axis: auto                     # x | y | z | auto
mesh_scale_factor: 1.0
resonance:     { Z_guidevanes: 18, max_harmonic: 6, margin_hz: 5.0,
                 margin_fraction: 0.05, penalty_k: 1.0 }
```

Shipped presets:

| Preset | Machine | BC template |
|---|---|---|
| `tistos.yaml` | Tistos Francis runner | `hub_clamp` |
| `canadaLight.yaml` | Laval full turbine | `free_free` |
| `naca.yaml` | NACA profile (2-D) | `foil_clamp` |

Load a preset directly:

```python
from eigenfrequencies.machines import load_machine

preset = load_machine("tistos")            # or a path to a YAML file
print(preset.material, preset.resonance)
```

Set `EIGENFREQUENCIES_MACHINES_DIR` to load presets from a different directory.

---

## Python API

The public surface is re-exported from the package root:

```python
from eigenfrequencies import (
    ModalResult, ModalAnalysisConfig, ResonanceConfig,
    MaterialConfig, BCConfig, MeshConfig, SolverConfig, WetModeConfig, OutputConfig,
    solve_modal, solve_modal_penalty, load_preset,
)
```

| Symbol | Purpose |
|---|---|
| `solve_modal(msh_path, config) -> ModalResult` | full modal analysis + penalty for one mesh |
| `solve_modal_penalty(msh_path, config) -> float` | scalar shortcut |
| `load_preset(machine, overrides) -> ModalAnalysisConfig` | machine preset + resonance overrides (must include `n_rpm`) |
| `ModalResult` | `frequencies_hz`, `resonance_penalty`, `violating_modes`, `band_report`, `metadata` |

`solve_modal` injects `msh_path` into the config mesh, applies `scale_factor` if it is not `1.0`,
and returns the frequencies as a tuple of Hz. `metadata` records the mesh path, rotation speed,
band settings, solver backend, element degree and mode count.

Provenance for a run can be captured with:

```python
from eigenfrequencies.provenance import generate

meta = generate(config)   # config snapshot, git commit/dirty, package/python version, timestamp
```

---

## Project layout

```
eigenfrequencies/
├── src/eigenfrequencies/
│   ├── api.py              ← solve_modal(), solve_modal_penalty(), load_preset(), ModalResult
│   ├── solve.py            ← thin CLI (python -m eigenfrequencies.solve)
│   ├── config.py           ← ModalAnalysisConfig + section dataclasses
│   ├── config_yaml.py      ← YAML loader/dumper + ConfigError
│   ├── schema.py           ← JSON-schema generator
│   ├── machines.py         ← machine-preset loader
│   ├── solver/             ← FEM modal solver (scipy / slepc)
│   ├── penalty/            ← band utilities (compute_penalty, band_report, violating_modes)
│   ├── io/                 ← mesh loading, axis inspection, result writers
│   ├── bc/                 ← boundary-condition builders
│   ├── materials/          ← material presets (steel, bronze)
│   ├── added_mass/         ← dry→wet frequency shift
│   ├── validation/         ← beam + Laval disc validation helpers
│   └── provenance.py       ← run metadata
├── adapters/machines/      ← machine presets (tistos, canadaLight, naca)
├── schema/                 ← generated JSON schema
├── tests/                  ← pytest suite
├── demo/beam/              ← cantilever-beam demo
├── cluster/                ← legacy SLURM scripts (see below)
├── docs/                   ← detailed documentation
└── showcase.py             ← step-by-step REPL walkthrough
```

---

## Validation

| Test case | Reference | Agreement |
|---|---|---|
| Cantilever beam (1 m steel, clamped) | Euler–Bernoulli analytical | ≤ 1 % |
| Laval bronze disc (d = 200 mm, hammer impact) | Experiment + ANSYS | ≤ 3 % |

```bash
pytest tests/validation/test_beam.py                  # needs a FEniCSx environment
RUN_TESTCASE_VALIDATION=1 pytest tests/validation/test_testcase.py
```

The full suite runs with the `dev` extra; tests requiring `dolfinx` are marked `requires_dolfinx`.

---

## showcase.py

`showcase.py` is written as a **step-by-step walkthrough**: top-level statements in `# %%` cells that
you can send one by one to a Python REPL (e.g. nvim + iron.nvim) and inspect the output of every
step — mesh check, mesh loading, modal solve, mode list, penalty and, finally, the one-call API.

---

## License

MIT — IHS University of Stuttgart.
