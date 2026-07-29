# Quickstart

This guide solves the built-in cantilever beam demo in five commands. The beam configuration lives at `examples/configs/beam.yaml` and uses a generated rectangular mesh with clamped boundary conditions.

## Prerequisites

You have already followed `docs/install.md` and activated the conda environment:

```bash
conda activate eigenfrequencies
```

## The five commands

1. **Activate the environment** (if not already active):

   ```bash
   conda activate eigenfrequencies
   ```

2. **Install the package** (editable, with all extras):

   ```bash
   uv pip install -e ".[optimize,mcp,dev]"
   ```

3. **Solve the beam**:

   ```bash
   eigenfrequencies solve --config examples/configs/beam.yaml --out output/beam
   ```

   This writes `output/beam/frequencies.json` with the first 10 eigenfrequencies and provenance metadata.

4. **Validate against analytical theory**:

   ```bash
   eigenfrequencies validate --suite beam
   ```

   The beam suite generates a 1 m cantilever mesh, runs a P2 modal solve, and compares bending-z modes against Euler-Bernoulli analytical frequencies. It passes if every mode is within 5 % tolerance.

5. **Print a summary report** (placeholder for optimization runs):

   ```bash
   eigenfrequencies report --run-dir output/beam
   ```

   For a plain solve directory, the report will note that no optimization result is present. After an optimization run, this command prints the best design vector, objective value, and evaluation count.

## What you should see

After step 3, the terminal prints a frequency table:

```
Frequencies (Hz):
  Mode 1: 4.1234 Hz
  Mode 2: 25.8362 Hz
  ...
```

After step 4, you should see:

```
Beam validation PASSED (all modes within 5% tolerance)
```

## Next steps

- Run a machine adapter: `docs/adapters.md`
- Start the MCP server: `docs/mcp.md`
- Submit to the cluster: `docs/cluster.md`
