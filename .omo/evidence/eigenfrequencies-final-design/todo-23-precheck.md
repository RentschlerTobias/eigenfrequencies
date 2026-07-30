# Todo 23 — naca pre-check

**Date**: 2026-07-29
**Case source**: git submodule `dtOO` (https://github.com/ihs-ustutt/dtOO.git)
**Commit**: `56e0ee4cbf83d15d105a0e2d0ef28d65a3fb13a0`
**Case root**: `dtOO/test/naca/`

## dtOO availability

- `git submodule update --init dtOO` succeeded — the submodule cloned from GitHub
  and checked out at commit `56e0ee4c` on 2026-07-29.
- `dtOOPythonSWIG` is NOT importable locally (expected — dtOO container only).
- Files present: `machine.xml`, `machineSave.xml`, `build.py`,
  `xml/` (11 XML includes), `cmp.sh`, 2 compressed mesh files.

## State inventory

| State | Source | Notes |
|-------|--------|-------|
| `init` | `machineSave.xml`, line 3 | Primary (and only) state. Loaded by `build.py` directly. |

**Conclusion**: `init` is the only buildable state — `build.py` uses it directly.

## Bounded volume

The naca case produces a **2-D blade-in-channel mesh** (not a 3-D turbine runner):

- **`gridGmsh`** — defined in `xml/gridMesh.xml` line 108
  - 2-D channel mesh with blade geometry extruded in the spanwise direction
  - Uses `dtMeshGRegion` for the volume and `dtMeshGRegionWithOneLayer` for BL refinement
  - Face patches include channel walls, inlet/outlet, and blade surfaces
  - **Recommended for 2-D foil validation** — simpler than the full 3-D runner mesh.

**Conclusion**: Use `gridGmsh` as the mechanical volume label.

## Adjust plugin

- No `dtPlugin` entries exist anywhere in `dtOO/test/naca/xml/`.
- The naca case has no domain-adjust plugin.

**Conclusion**: Set `adjust_plugin` to the empty string `""`. The naca case does not require a domain-adjust step.

## Design labels (init state)

The `machineSave.xml` state `init` defines the following foil-blade design parameters:

### Foil profile (2-D, no spanwise sections)
- `cV_alpha_1_ex` — inlet angle extension (sliderFloatParam, min=-5, max=10)
- `cV_alpha_2_ex` — outlet angle extension (sliderFloatParam, min=-5, max=5)
- `cV_M_ex` — camber / Mach extension (sliderFloatParam, min=-0.05, max=0.05)
- `cV_offsetM_ex` — camber offset (constrainedFloatParam, formula: cV_L/2, min=-0.6, max=0)
- `cV_offsetPhiR_ex` — stagger angle offset (constrainedFloatParam, formula: 0.5·2π·cV_R/cV_nBlades, min=-0.15, max=0.15)
- `cV_ratio` — solidity / thickness ratio (sliderFloatParam, min=0.4, max=0.6)
- `cV_bladeLength` — chord length (sliderFloatParam, min=0.1, max=2.0)

### Blade thickness profile
- `cV_maxThickness_a`, `cV_maxThickness_b` — max thickness params
- `cV_thick_x`, `cV_thick_y` — thickness distribution control points
- `cV_t_tip_a`, `cV_u_max_a`, `cV_t_max_a`, `cV_u_te_a`, `cV_t_te_a` — pressure-side profile
- `cV_t_tip_b`, `cV_u_max_b`, `cV_t_max_b`, `cV_u_te_b`, `cV_t_te_b` — suction-side profile

### Mesh / channel parameters
- `cV_meshBlockThickness`, `cV_divideInternalMeshBlock_*` — mesh block controls
- `cV_nBlades` (= 4), `cV_nElemTangentialBlade`, `cV_nElemNormalBlade`, etc.

## Machine YAML design decisions

- **state**: `init` (only state available)
- **mech_volume**: `gridGmsh` (2-D blade-in-channel mesh)
- **adjust_plugin**: `""` (no plugin defined in naca case)
- **bc_template**: `foil_clamp` (task requirement — axial-plane clamp at z=0, simulating disc validator with foil root constrained)
- **axis**: `auto` (rotation axis discovered from BB)
- **mesh_scale_factor**: `1.0` (unknown; dtOO meshes are assumed to be in metres)
- **design**: 7 foil-blade profile parameters — `cV_alpha_1_ex`, `cV_alpha_2_ex`, `cV_M_ex`, `cV_offsetM_ex`, `cV_offsetPhiR_ex`, `cV_ratio`, `cV_bladeLength`
- **case_dir**: relative `dtOO/test/naca` (repo root); tests resolve to absolute path via `Path(__file__).parent.parent.parent`
