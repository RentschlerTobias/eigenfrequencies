# turbine_runner

Couple **dtOO** (parametric hydraulic-machine geometry) to **FEniCSx** to compute,
and then optimize away resonance in, a turbine runner's structural eigenfrequencies.

- **Step 1** — dtOO geometry → eigenfrequencies (`dtoo_export.py` → `main.py`).
- **Step 2** — drive dtOO design params so no eigenfrequency lands in a forbidden
  band (`optimize.py`).

## Three stages, two containers

dtOO and FEniCSx live in different containers and never run together; they are
linked by `.msh` / `.json` files in `data/` (the shared volume). The optimizer
(stage 3) runs on the host and `docker run`s the two images per evaluation.

```
[dtOO container]                       [fenicsx container]
atismer/dtoo-opensuse:stable           eigenfrequencies-fenicsx:latest
  dtoo_export.py ─▶ data/runner.msh ─▶ main.py / evaluate.py ─▶ frequencies
        ▲                                              │
   data/design.json ◀───────── optimize.py (host, /root/venv) ◀── penalty
```

### Stage 1 — generate geometry (dtOO container)

Geometry-only (no CFD): builds `ruWithRounding_mechMesh` → `data/runner.msh`.
Reads optional `data/design.json` ({label: value}) to override dtOO design params.

```bash
docker run --rm \
  -v "$PWD/turbine_runner/data:/work" \
  -v "$PWD/turbine_runner:/src" \
  -w /dtOO/test/tistos \
  atismer/dtoo-opensuse:stable \
  bash -lc 'export LD_LIBRARY_PATH=/dtOO-install/lib:/dtOO-install/lib64:$LD_LIBRARY_PATH \
            && python3.12 /src/dtoo_export.py'
```

Container specifics that MUST be honored (otherwise import errors):
- interpreter is **`python3.12`** (OCC needs numpy 2.x; `python3`/3.6 fails)
- **`LD_LIBRARY_PATH`** must include `/dtOO-install/lib` (OpenCASCADE) + `/lib64` (gmsh)
- run under **`bash -lc`** so the OpenFOAM environment is sourced
- workdir is a dtOO case dir holding `machine.xml`/`machineSave.xml`/`xml/`
  (baked into the image at `/dtOO/test/tistos`)

Override via env: `DTOO_CASE_DIR`, `DTOO_STATE`, `DTOO_MECH_VOLUME`,
`DTOO_ADJUST_PLUGIN`, `DTOO_DESIGN_JSON`, `DTOO_OUTPUT_MSH`.

> **Not the CFD mesh:** `block_structured_meshing/T1_9/T1_9_ru_gridGmsh.msh` is the
> *fluid* flow-channel mesh, **not** a structural solid — only a smoke-test input.

### Stage 2 — eigenfrequencies (fenicsx container)

```bash
docker run --rm -e PYTHONUNBUFFERED=1 \
  -v "$PWD:/workspace" -w /workspace/turbine_runner \
  eigenfrequencies-fenicsx:latest \
  python3 main.py            # full report + XDMF/VTK/JSON
#  python3 evaluate.py data/runner.msh   # headless: frequencies JSON only
```

### Stage 3 — resonance-avoidance optimization (host)

Needs a host python with numpy+scipy (use `/root/venv/bin/python`) and docker.

```bash
OPT_FMIN=100 OPT_FMAX=150 OPT_MAX_ITER=40 \
  /root/venv/bin/python turbine_runner/optimize.py
```

Forbidden band + design params are set in `config.py`
(`OptimizationConfig`, `DesignConfig`); env `OPT_FMIN/OPT_FMAX/OPT_MAX_ITER`
override for quick runs. Result → `output/optimization.json`.

## Set the boundary condition first

The dtOO mesh is in scaled, non-physical coordinates and its rotation axis is
**not** along x (unlike the beam demo). Run the axis-discovery diagnostic once
after the first export:

```bash
# inside the fenicsx container, in turbine_runner/
python3 mesh_prep.py
```

It prints the coordinate bbox and per-axis spans. Use them to set `BCConfig` in
`config.py`:

- `axis` — the rotation axis (usually the longest span)
- `hub_radius`, `hub_center` — radial clamp region around the axis
- `axial_min` / `axial_max` — restrict the clamp to the hub bore band
- or `mode="axial_plane"` + `plane_value` to clamp a single plane

## Verification checklist

1. `data/runner.msh` exists and is non-trivial in size.
2. Element histogram shows volume cells (gmsh tet types 4 or 11). If only
   tri/quad appear, the `mesh_prep` volume-meshing fallback runs (needs a
   `step_path`, or a closed surface mesh).
3. `mesh_prep` logs `topology.dim == 3`.
4. Solver logs **fixed DOFs > 0** and a clamped-node bbox located at the hub.
5. Lowest ~6 frequencies are **real and positive** (near-zero values ⇒ rigid-body
   modes ⇒ the clamp failed; fix `BCConfig`).
6. `output/modes.xdmf` opens in ParaView with sensible blade deformation.

## Files

| File | Stage | Role |
|------|-------|------|
| `config.py` | — | Material / BC / Mesh / Solver / Output dataclasses |
| `dtoo_export.py` | 1 (dtOO) | Drive dtOO, export `runner.msh` |
| `mesh_prep.py` | 2a (fenicsx) | Load + verify volume mesh + fallback; axis diagnostic |
| `solver.py` | 2b (fenicsx) | `RunnerModalSolver` (sparse, config-driven hub clamp) |
| `main.py` | 2 (fenicsx) | Orchestrate, print, write XDMF + JSON |
