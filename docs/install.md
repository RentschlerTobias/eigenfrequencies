# Installation

Eigenfrequencies is a Python package for structural modal analysis of hydraulic turbine runners. It depends on FEniCSx (dolfinx), which is distributed through conda-forge, not PyPI. The recommended install path uses conda for the heavy scientific stack and `uv` for fast Python package management.

## Primary path: conda + uv

1. Create the conda environment from the bundled spec:

   ```bash
   conda env create -f environment.yml
   ```

2. Activate it:

   ```bash
   conda activate eigenfrequencies
   ```

3. Install the package and its extras with `uv`:

   ```bash
   uv pip install -e ".[optimize,mcp,dev]"
   ```

   The `optimize` extra pulls in `optuna`, `pymoo`, and `cma`. The `mcp` extra pulls in `fastmcp` for the MCP server. The `dev` extra pulls in `pytest`, `ruff`, and `jsonschema`.

4. Verify the CLI is on your path:

   ```bash
   eigenfrequencies --help
   ```

## Docker path (local development)

If you prefer containers or need a reproducible environment without managing conda channels:

```bash
./scripts/build_container.sh   # builds eigenfrequencies-fenicsx:latest
./scripts/run_container.sh     # drops you into /workspace with the repo mounted
```

Inside the container, the package is already installed via `uv pip install .[optimize,mcp,dev]`.

## Cluster path: bwUniCluster 3.0 with enroot

On the cluster, FEniCSx is provided through an enroot/Pyxis container (`pyxis_fenicsx`) imported from `docker://dolfinx/dolfinx:stable`. The dtOO + OpenFOAM stack lives in a separate environment (`source ~/pe`). The two stacks do not coexist in one environment. See `docs/cluster.md` for full sbatch orchestration.

Quick cluster sanity check:

```bash
enroot start -m "$PWD:/workspace" pyxis_fenicsx \
    bash -c 'python3 -c "import dolfinx; print(dolfinx.__version__)"'
```

## What is NOT supported

- **PyPI-only install**: `dolfinx` is not on PyPI, so `pip install eigenfrequencies` without a conda environment will fail.
- **System Python**: The package requires Python 3.11–3.13 and the conda-forge scientific stack. Do not attempt to install into a bare system Python.
