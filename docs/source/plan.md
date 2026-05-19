# Project Plan: Eigenfrequencies Framework

## Phase 1: Project Infrastructure

### 1.1 Repository Structure

```
eigenfrequencies/
├── src/
│   ├── geometry/       # gmsh wrapper
│   ├── solver/         # FEniCSx modal analysis
│   ├── optimization/   # pygmo integration
│   └── io/             # XDMF read/write
├── docs/
│   └── source/
│       ├── index.rst
│       ├── quickstart.md
│       ├── theory/
│       └── api/
├── demo/
│   ├── beam/           # Beam demo (Phase 2+3)
│   └── turbine_blade/  # Turbine blade (later)
├── test/
├── docker/
│   └── fenicsx.Dockerfile
└── dtOO/               # Submodule (full)
```

### 1.2 Docker Containers

| Container | Content |
|-----------|---------|
| fenicsx.Dockerfile | FEniCSx + SLEPc + pygmo + gmsh |

Note: dtOO Docker container will be created in Phase 4 when needed.

### 1.3 Python Build: pyproject.toml

### 1.4 CI/CD: GitHub Actions

### 1.5 Documentation: Sphinx + Markdown → GitHub Pages

---

## Phase 2: Geometry (independent of dtOO)

### 2.1 gmsh Python-API

- Simple beam: rectangular cross-section
- Parameters: Length (L), Width (B), Height (H)
- Material: E-modulus, density

### 2.2 Export → XDMF

---

## Phase 3: FEniCSx Solver

| Parameter | Value |
|-----------|-------|
| Installation | Docker (dolfinx/dolfinx:stable) + bash scripts |
| Element | Lagrange P2 |
| Boundary Condition | Clamped (fixed support) |
| Validation | Convergence study: mesh refinement vs. analytical solution |
| Output | Text + XDMF + VTK |
| Solver Parameters | Configurable frequency range |

### Analytical Validation (Euler-Bernoulli)

$$f_n = \frac{\alpha_n^2}{2\pi} \sqrt{\frac{EI}{\rho S L^4}}$$

where $\alpha_n$ are the solutions of $\tan(\alpha) = \alpha$.

---

## Phase 4: Optimization

| Parameter | Value |
|-----------|-------|
| Framework | pygmo |
| Cost Function | Exact Match (hit specific frequency) |
| | Avoidance (avoid interval) |

Note: dtOO integration and dtoo.Dockerfile added in this phase.

---

## Phase 5: dtOO Integration (later)

- Complex geometries from dtOO
- Fluid-structure interaction (Helmholtz equation)
- Cluster deployment

---

## Technology Stack

| Component | Software |
|-----------|----------|
| Geometry | gmsh 4.x (Python-API) |
| Mesh Format | XDMF + HDF5 |
| FEM Solver | FEniCSx + SLEPc |
| Optimization | pygmo |
| Documentation | Sphinx + Markdown |
| CI/CD | GitHub Actions |