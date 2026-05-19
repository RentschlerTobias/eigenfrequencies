# Beam Geometry Documentation

This file documents the geometry generation using Gmsh's OCC (OpenCascade) kernel.

## Overview

The geometry module creates a rectangular beam mesh for modal analysis. It uses Gmsh's CAD kernel to create a 3D box geometry, then generates a finite element mesh with local refinement at the boundaries.

## create_rectangular_beam()

Creates a rectangular beam geometry in Gmsh's OCC kernel.

```python
def create_rectangular_beam(config: BeamConfig) -> Tuple[int, int, int]:
```

### OCC Box Creation

```python
occ.addBox(-L2, -B2, -H2, L, B, H)
```

This creates a box (cuboid) in the CAD model. The parameters are:

```
occ.addBox(xmin, ymin, zmin, dx, dy, dz)
                ↓
           (-L/2, -B/2, -H/2,  L,   B,   H)
```

| Parameter | Value | Meaning |
|-----------|-------|---------|
| xmin | -L/2 | Left face at x = -L/2 |
| ymin | -B/2 | Bottom face at y = -B/2 |
| zmin | -H/2 | Back face at z = -H/2 |
| dx | L | Length in x-direction |
| dy | B | Width in y-direction |
| dz | H | Height in z-direction |

### Visualization

```
            y
            ↑
            │
         B/2 ●───────────────┬───────────────┐
            │                │               │
            │                │               │
            │                │               │
    -L/2 ───┼────────────────┼───────────────┼──→ x
            │                │               │
            │                │               │
         -B/2●───────────────┴───────────────┘
           /
          /
         z

The beam is centered around the origin (0,0,0)
Length L, Width B, Height H
```

### Physical Group

After creating the box, a physical group is created:
```python
volume = model.addPhysicalGroup(3, [1])
model.setPhysicalName(3, volume, "Beam")
```

This assigns the tag "Beam" to the 3D volume (dimension 3), which will be used later for boundary conditions.

### Return Values

- `volume_tag`: Always 1 (the single volume)
- `surface_tags`: List of all 2D surface tags
- `line_tags`: List of all 1D line tags

These are collected by iterating over all entities in the model after `occ.synchronize()`.

---

## set_mesh_resolution()

Sets local mesh size constraints on geometric points.

```python
def set_mesh_resolution(config: BeamConfig) -> None:
```

### Mesh Refinement Strategy

The function applies a finer mesh resolution near the beam ends:

```python
dist_to_end = min(abs(x + L/2), abs(x - L/2))
if dist_to_end < L * 0.1:
    local_size = mesh_size * 0.5
else:
    local_size = mesh_size
```

| Zone | Distance from end | Mesh size |
|------|-------------------|-----------|
| Near end | < 10% of length | 50% of base size |
| Interior | ≥ 10% of length | Base size |

### Why refine the ends?

At the clamped boundary (x=0), stress concentrations occur. A finer mesh captures these high-stress regions more accurately.

### How it works

1. Get all 0-dimensional entities (points)
2. For each point, get its x-coordinate
3. Calculate distance to nearest beam end
4. Set mesh size accordingly

---

## generate_mesh()

Main entry point for mesh generation.

```python
def generate_mesh(config: BeamConfig, output_path: str) -> str:
```

### Pipeline

```
gmsh.initialize()
    ↓
gmsh.option.setNumber("Mesh.Algorithm", 6)  # Frontal-Delaunay
    ↓
gmsh.model.add("beam")
    ↓
create_rectangular_beam(config)  # CAD geometry
    ↓
set_mesh_resolution(config)  # Mesh size constraints
    ↓
gmsh.model.occ.synchronize()  # Sync OCC with meshing
    ↓
gmsh.write(output_path + "/beam.msh")  # Save mesh
    ↓
gmsh.finalize()
```

### Mesh.Algorithm = 6

The algorithm 6 is **Frontal Delaunay** (Mesh.Algorithm = 6). This is suitable for 3D tetrahedral meshes with good quality in complex geometries.

### Output

Returns the path to the generated `.msh` file (Gmsh's native format).

---

## beam_to_xdmf()

Placeholder function for mesh format conversion.

```python
def beam_to_xdmf(config: BeamConfig, output_dir: str) -> str:
```

Currently returns the `.msh` path. The actual XDMF conversion is handled by FEniCSx's `gmshio` module in the solver.

---

## Relationship to Solver

The generated mesh is loaded in `solver.py` using:

```python
from dolfinx.io import gmshio
mesh, cell_tags, facet_tags = gmshio.read_msh(mesh_file, rank=0)
```

The `cell_tags` and `facet_tags` contain information about physical groups (like "Beam" and the surfaces) which are used to apply boundary conditions.