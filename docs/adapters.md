# Machine Adapters

A machine adapter connects a dtOO parametric geometry case to the eigenfrequencies solver. It describes the case directory, the state to load, the mechanical volume label, design-parameter bounds, and boundary-condition templates.

## Authoring a machine YAML

Create a YAML file with the following fields. Every field is validated on load; unknown keys or `min > max` bounds raise `ConfigError`.

### Required fields

| Field | Type | Description |
|-------|------|-------------|
| `name` | string | Human-readable machine identifier |
| `case_dir` | string | Path to the dtOO case directory (must contain `machine.xml` + `machineSave.xml` + `xml/`) |
| `state` | string | dtOO state name to load (e.g. `templateState`) |
| `mech_volume` | string | Bounded-volume label for the structural mesh (e.g. `ruWithRounding_mechMesh`) |
| `adjust_plugin` | string | dtPlugin label that finalises the geometry (e.g. `ru_adjustDomain`) |
| `design` | mapping | `{label: {min: float, max: float}}` exposing parametric degrees of freedom to the optimizer |

### Optional fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `mesh_scale_factor` | float | `1.0` | Linear scale factor applied to exported mesh coordinates to recover physical units |
| `bc_template` | string or dict | `hub_clamp` | Boundary-condition template (see below) |
| `axis` | string or list | `auto` | Rotation axis. `"auto"` discovers from mesh bounding box (longest span). An explicit 3-vector `[x, y, z]` is used directly |

### Example minimal machine file

```yaml
name: my_runner
case_dir: ~/dtOO/build/test/my_case
state: templateState
mech_volume: ruWithRounding_mechMesh
adjust_plugin: ru_adjustDomain
design:
  cV_ru_bladeLength_0.5:
    min: 0.6
    max: 1.0
mesh_scale_factor: 1.0
bc_template: hub_clamp
axis: auto
```

## Scale-factor workflow with `measure-scale`

dtOO meshes are often written in native units that do not map 1:1 to metres. The `mesh_scale_factor` rescales coordinates after export.

1. Export the mesh once with the adapter (or use an existing `.msh`):

   ```bash
   # inside the dtOO container, or after export
   ls data/runner.msh
   ```

2. Measure a known physical feature with the CLI:

   ```bash
   eigenfrequencies dtoo measure-scale \
       --mesh data/runner.msh \
       --physical-length 0.15 \
       --feature-desc "hub bore diameter"
   ```

   This prints a YAML snippet:

   ```yaml
   mesh_scale_factor: 0.00362342  # hub bore diameter
   ```

3. Paste the snippet into your machine YAML.

## Boundary-condition templates

Three templates are shipped. Each maps to a `BCConfig` via the builder functions in `eigenfrequencies.bc.builders`.

### `hub_clamp`

Radius-band clamp at the runner hub. Nodes within `hub_radius` of the rotation axis are fixed. Optional `axial_min` / `axial_max` restrict the clamp to an axial band.

```yaml
bc_template:
  type: hub_clamp
  params:
    hub_center: [0.0, 0.0]
    hub_radius: 0.15
    axial_min: null
    axial_max: null
```

### `foil_clamp`

Axial-plane clamp (e.g. a foil disc fixed at `z=0`). All nodes within `plane_tol` of `plane_value` on the rotation axis are fixed.

```yaml
bc_template:
  type: foil_clamp
  params:
    plane_value: 0.0
    plane_tol: 1.0e-6
```

### `free_free`

No clamp at all. The 6 rigid-body modes are expected and must be discarded downstream. Used for experimental validation against free-free test data.

```yaml
bc_template: free_free
```

## Shipped machine adapters

Three machine YAMLs live under `adapters/machines/`.

### `tistos.yaml`

- **Machine**: Tistos Francis runner
- **Design parameters**: 30 (full spanwise set: alpha, offset, ratio, bladeLength, thickness, u-mid at hub/mid/shroud)
- **BC**: `hub_clamp` with `hub_radius: 0.15`
- **Scale factor**: `1.0` (placeholder — must be updated after running `measure-scale` inside the dtOO container)
- **Caveat**: The dtOO mesh coordinates are in native units. Do not trust frequencies until the scale factor is calibrated.

### `canadaLight.yaml`

- **Machine**: canadaLight full turbine (guide vane, runner, draft tube)
- **Design parameters**: 21 (7 parameters × 3 spanwise sections)
- **BC**: `free_free` (no clamp; modal analysis only)
- **Scale factor**: `1.0` (assumes dtOO mesh is already in metres)
- **Caveat**: `free_free` produces 6 rigid-body modes near 0 Hz. Discard them before reading the elastic spectrum.

### `naca` (planned)

- **Machine**: NACA foil test case (simplified geometry for method validation)
- **Design parameters**: TBD
- **BC**: TBD
- **Caveat**: Not yet shipped. Use `tistos.yaml` or `canadaLight.yaml` for production work.

## Loading a machine adapter in Python

```python
from eigenfrequencies.adapters.dtoo.adapter import DtooAdapter

adapter = DtooAdapter("adapters/machines/tistos.yaml")
mesh_path = adapter.export_mesh({"cV_ru_bladeLength_0.5": 0.75})
bc_cfg = adapter.bc()
bounds = adapter.design_bounds()
```

The adapter defers the heavy dtOO import until `export_mesh()` is called, so the class is safe to import in environments without dtOO installed.
