# eigenfrequencies

Eigenfrequency analysis toolkit for hydraulic turbine components.

Optimises blade-design parameters to avoid resonant frequencies across all
harmonic orders up to `max_harmonic` at a given operating RPM, using
gradient-free differential evolution (DE). Suitable for research and
industrial pre-design studies.

## Validation highlights

| Test case      | Method              | Agreement vs reference |
|---------------|---------------------|------------------------|
| Cantilever beam | Euler–Bernoulli FEM | ≤ 1 % vs analytical    |
| Laval disc     | 3-D FE modal        | ≤ 3 % vs ANSYS / experiment |

See `src/eigenfrequencies/validation/` for test definitions.

## Install

```bash
conda env create -f environment.yml
conda activate eigenfrequencies

# or with uv (faster)
uv env create -f pyproject.toml
uv pip install -e .
```

Full installation guide: `docs/install.md`

## Quickstart

Solve the beam demo (inside the container or on a machine with FEM libraries):

```bash
eigenfrequencies solve examples/configs/beam.yaml
eigenfrequencies validate examples/configs/beam.yaml
eigenfrequencies optimize examples/configs/beam.yaml --de
eigenfrequencies report output/frequencies.json
```

## Machine adapters

Adapters provide machine-specific geometry, design bounds, and boundary
conditions:

| Adapter        | Description |
|---------------|-------------|
| `tistos`      | Francis-style runner, 30 design parameters, hub-clamp BC |
| `canadaLight` | Full turbine (guide vane + runner + draft tube), 21 parameters, free–free modal BC |
| `naca`        | NACA-airfoil benchmark blade (planned) |

Pass any adapter config to `solve` / `optimize`:

```bash
eigenfrequencies solve adapters/machines/tistos.yaml
```

## MCP server

Embed `eigenfrequencies` as a stdio MCP server in any AI coding tool:

```bash
eigenfrequencies mcp
```

## Roadmap

| Feature               | Status |
|-----------------------|--------|
| Dry modal analysis    | Done   |
| Differential evolution optimisation | Done |
| Fluid–structure coupling (wet/FSI) | Future work |
| Multi-objective NSGA-II | Future work |
| PyPI / conda-forge release | Future work |

## Project layout

```
src/eigenfrequencies/
├── adapters/          # Machine geometry + BC adapters
├── cli.py             # typer CLI entry point
├── config*.py         # Defaults + presets
├── io/                # Mesh / result I/O (Gmsh, XDMF, VTK)
├── mcp/               # MCP job-store for agent integration
├── materials/         # Steel, cast-iron, concrete material data
├── optimize/          # DE wrapper, penalty schemes
├── solver/            # SLEPc eigenvalue solver
├── validation/         # Beam and Laval test cases
└── bc/                # Boundary-condition helpers
```

## License

MIT — IHS University of Stuttgart.
