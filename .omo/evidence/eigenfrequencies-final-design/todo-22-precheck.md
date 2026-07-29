# Todo 22 — canadaLight pre-check

**Date**: 2026-07-29
**Case source**: git submodule `dtOO` (https://github.com/ihs-ustutt/dtOO.git)
**Commit**: `56e0ee4cbf83d15d105a0e2d0ef28d65a3fb13a0`
**Case root**: `dtOO/test/canadaLight/`

## dtOO availability

- `git submodule update --init dtOO` succeeded — the submodule cloned from GitHub
  and checked out at commit `56e0ee4c` on 2026-07-29.
- `dtOOPythonSWIG` is NOT importable locally (expected — dtOO container only).
- Files present: `machine.xml`, `machineSave.xml`, `E1_12685.xml`, `init.xml`,
  `build.py`, `xml/` (43 XML includes), `geo/` (2 IGES edges), `Mesh/` (1 CGNS).

## State inventory

| State | Source | Notes |
|-------|--------|-------|
| `E1_12685` | `machineSave.xml`, `E1_12685.xml` | Primary state. Loaded by `build.py` via `parser.loadStateToConst("E1_12685", cV)`. Contains full sliderFloatParam definitions with min/max bounds. |
| `E1_12685_iceCube` | `machineSave.xml` | Alternate state with iceCube-specific overrides. |
| `init` | `init.xml` | Initial state with different default values. |
| `init_ext` | `init.xml` | Extended initial state. |

**Conclusion**: `E1_12685` is the primary buildable state — `build.py` uses it directly.

## Solid/mechanical volume

Two bounded-volume labels produce 3-D tetrahedral meshes via gmsh `dtMeshGRegion`:

1. **`ruWithRounding_mechMesh`** (from `xml/ruWithRounding_mechMesh.xml`)
   - Includes runner blade geometry with TE rounding
   - Uses `boundedVolume name="customGmsh"` with `dtMeshGRegion` for tetrahedral volume mesh
   - Writes both `.msh` and `.inp` files at orders 1 and 2
   - Face patches: `RUHUB`, `RU_HUB_FIX`, `RUBLADE` — labelled regions suitable for BC assignment
   - **Recommended for modal analysis** — captures the full runner blade geometry.

2. **`ru_mechGridGmsh`** (from `xml/ru_mechMesh.xml`)
   - Hub-only mesh (no blade geometry)
   - Simpler cylinder-like mesh — not suitable for structural modal analysis of the runner.

**Conclusion**: Use `ruWithRounding_mechMesh` as the mechanical volume label.

## Adjust plugin

- `ru_adjustDomain` — defined in `xml/ru_gridChannel.xml` (label found via grep)
- `gv_adjustDomain` — defined in `xml/gv_gridChannel.xml` (guide vane domain)

**Conclusion**: Use `ru_adjustDomain` as the domain-adjust plugin that finalises the runner geometry before meshing.

## Design labels (E1_12685 state)

The `machineSave.xml` state `E1_12685` defines ~350+ const-values, including many
`sliderFloatParam`s with min/max bounds.  The following runner-blade design parameters
were identified from the `cV_ru_*` namespace:

### Blade profile (spanwise sections at 0%, 50%, 100%)
- `cV_ru_alpha_1_ex_0.0`, `cV_ru_alpha_1_ex_0.5`, `cV_ru_alpha_1_ex_1.0` — inlet angle
- `cV_ru_alpha_2_ex_0.0`, `cV_ru_alpha_2_ex_0.5`, `cV_ru_alpha_2_ex_1.0` — outlet angle
- `cV_ru_M_ex_0.0`, `cV_ru_M_ex_0.5`, `cV_ru_M_ex_1.0` — Mach number / camber
- `cV_ru_offsetM_ex_0.0`, `cV_ru_offsetM_ex_0.5`, `cV_ru_offsetM_ex_1.0` — camber offset
- `cV_ru_offsetPhiR_ex_0.0`, `cV_ru_offsetPhiR_ex_0.5`, `cV_ru_offsetPhiR_ex_1.0` — stagger angle offset
- `cV_ru_ratio_0.0`, `cV_ru_ratio_0.5`, `cV_ru_ratio_1.0` — solidity/thickness ratio
- `cV_ru_bladeLength_0.0`, `cV_ru_bladeLength_0.5`, `cV_ru_bladeLength_1.0` — blade chord length

### Blade thickness (pressure side / suction side)
- `cV_ru_maxThickness_a_0`, `cV_ru_maxThickness_a_1`
- `cV_ru_maxThickness_b_0`, `cV_ru_maxThickness_b_1`

### Blade thickness profile (2D profile control points)
- `cV_ru_t_tip_a_0`, `cV_ru_t_tip_b_0`, `cV_ru_t_tip_a_1`, `cV_ru_t_tip_b_1`
- `cV_ru_u_max_a_0`, `cV_ru_u_max_b_0`, `cV_ru_u_max_a_1`, `cV_ru_u_max_b_1`
- `cV_ru_t_max_a_0`, `cV_ru_t_max_b_0`, `cV_ru_t_max_a_1`, `cV_ru_t_max_b_1`
- `cV_ru_u_te_a_0`, `cV_ru_u_te_b_0`, `cV_ru_u_te_a_1`, `cV_ru_u_te_b_1`
- `cV_ru_t_te_a_0`, `cV_ru_t_te_b_0`, `cV_ru_t_te_a_1`, `cV_ru_t_te_b_1`

### Membrane control points
- `cV_ru_mplane_0`, `cV_ru_mplane_100`, `cV_ru_mplane_250`, `cV_ru_mplane_500`,
  `cV_ru_mplane_750`, `cV_ru_mplane_900`, `cV_ru_mplane_1000`

### Mesh resolution (intParams, not sliderFloatParams)
- `cV_ru_nBlades` (= 4)
- `cV_ru_nElemTangentialBlade`, `cV_ru_nElemTangentialTip`, ...
- `cV_ru_charLMin`, `cV_ru_charCLMax`, `cV_ru_lcIntPrec`

## Machine YAML design decisions

- **state**: `E1_12685` (build.py default)
- **mech_volume**: `ruWithRounding_mechMesh` (solid blade geometry)
- **adjust_plugin**: `ru_adjustDomain` (finalises runner domain)
- **bc_template**: `free_free` (task requirement — no clamp, modal analysis)
- **axis**: `auto` (rotation axis along Z, discovered from BB)
- **mesh_scale_factor**: `1.0` (unknown; dtOO meshes are assumed to be in metres)
- **design**: 21 spanwise blade parameters — the `cV_ru_alpha_*`, `cV_ru_M_*`,
  `cV_ru_offsetM_*`, `cV_ru_offsetPhiR_*`, `cV_ru_ratio_*`, `cV_ru_bladeLength_*`
  across 3 spanwise sections (hub=0.0, mid=0.5, tip=1.0)
- **case_dir**: relative `dtOO/test/canadaLight` (repo root); tests resolve to
  absolute path via `Path(__file__).parent.parent.parent`
