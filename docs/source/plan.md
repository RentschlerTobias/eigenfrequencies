# Ablaufplan: Eigenfrequenzen-Framework

## Phase 1: Projekt-Infrastruktur

### 1.1 Repository-Struktur

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
│   ├── beam/           # Balken demo (Phase 2+3)
│   └── turbine_blade/  # Turbine blade (später)
├── test/
├── docker/
│   ├── dtoo.Dockerfile
│   └── fenicsx.Dockerfile
└── dtOO/               # Submodul (ganz)
```

### 1.2 Docker-Container

| Container | Inhalt |
|-----------|--------|
| dtoo.Dockerfile | dtOO + gmsh + Python |
| fenicsx.Dockerfile | FEniCSx + SLEPc + pygmo |

### 1.3 Python-Build: pyproject.toml

### 1.4 CI/CD: GitHub Actions

### 1.5 Dokumentation: Sphinx + Markdown → GitHub Pages

---

## Phase 2: Geometrie (unabhängig von dtOO)

### 2.1 gmsh Python-API

- Einfacher Balken: Rechteck-Querschnitt
- Parameter: Länge (L), Breite (B), Höhe (H)
- Material: E-Modul, Dichte

### 2.2 Export → XDMF

---

## Phase 3: FEniCSx Solver

| Parameter | Wert |
|-----------|------|
| Installation | Docker (hierarchical finite elements/fenicsx:stable) |
| Element | Lagrange P2 |
| Randbedingung | Clamped (eingespannt) |
| Validierung | Konvergenzstudie: Mesh-Verfeinerung vs. analytische Lösung |
| Output | Text + XDMF + VTK |
| Solver-Parameter | Konfigurierbarer Frequenzbereich |

### Analytische Validierung (Euler-Bernoulli)

$$f_n = \frac{\alpha_n^2}{2\pi} \sqrt{\frac{EI}{\rho S L^4}}$$

wobei $\alpha_n$ die Lösungen von $\tan(\alpha) = \alpha$ sind.

---

## Phase 4: Optimierung

| Parameter | Wert |
|-----------|------|
| Framework | pygmo |
| Cost Function | Exact Match (bestimmte Frequenz treffen) |
| | Avoidance (Intervall vermeiden) |

---

## Phase 5: Integration mit dtOO (später)

- Komplexere Geometrien aus dtOO
- Fluid-Struktur-Wechselwirkung (Helmholtz-Gleichung)
- Cluster-Deployment

---

## Technologie-Stack

| Component | Software |
|-----------|----------|
| Geometrie | gmsh 4.x (Python-API) |
| Mesh-Format | XDMF + HDF5 |
| FEM-Solver | FEniCSx + SLEPc |
| Optimierung | pygmo |
| Dokumentation | Sphinx + Markdown |
| CI/CD | GitHub Actions |