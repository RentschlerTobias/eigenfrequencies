# Installation

Eigenfrequencies is a Python package for structural modal analysis of hydraulic turbine runners. It depends on FEniCSx (dolfinx), which is distributed through conda-forge, not PyPI.

## Recommended: the pipeline image

`duty/hydrostack` builds one Apptainer image containing this package together with dtOO + OpenFOAM, AlgoHex and torch, and it is the only path that gives you the whole pipeline in one place:

```bash
cd duty/hydrostack
cp stack.conf.example stack.conf
./install.sh --build
./bin/stack-run cfd-opt profiles/local.toml --dry-run
```

See [`duty/hydrostack/README.md`](../../hydrostack/README.md). That image is also what makes the claim below — that the dtOO and FEniCSx stacks do not coexist — testable rather than merely inherited: the two live in one filesystem there, in separate venvs, kept apart by the per-stage setup constants in `src/eigenfrequencies/hydroflow/physics.py`.

The paths below remain supported and are what the cluster runs today.

## conda + uv

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
- **dtOO and FEniCSx in one conda environment**: they do not coexist there, which is why the cluster keeps them in separate containers. The pipeline image takes a different approach — one filesystem, two venvs, per-stage environments — rather than contradicting this.
