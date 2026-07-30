---
status: deferred
scope: orthogonal accelerations (parallel solves, P2), additional physics (wet modes, kinematic band), long-horizon research (NSGA-II, FSI)
related_files:
  - turbine_runner/added_mass.py (`rayleigh_ratios`)
  - turbine_runner/solver.py (`element_degree`)
  - turbine_runner/optimization.py (band logic)
  - cfd/ (OF case dirs for decomposePar)
  - de_framework (parallel patterns to reuse)
detail_of: "[[obsidian_dashboard_eigenfrequencies#5. Phase 4 deferred]]"
---

# Phase 4 deferred

Items from PROGRESS §Phase 4 + long-term research originally in dashboard "Optional / Long-term".

## Sub-items

- [ ] OpenFOAM parallel: `decomposeParDict` per worker case, `mpirun simpleFoam -parallel`
- [ ] FEniCSx parallel: SLEPc / primme backend for eigenvalue solve
- [ ] P1 vs P2 convergence: `SolverConfig.element_degree=2` on a high-mem node
- [ ] Wet modes: implement real `added_mass.rayleigh_ratios` — dolfinx fluid-domain Laplace solve, wetted-surface tagging (currently `placeholder_ratios` ~15 % shift)
- [ ] Kinematic blade-passing band: auto-derive `Z_guidevanes · n`, update forbidden band logic
- [ ] NSGA-II: if scalarization limiting (see [[eigenfrequencies_todos/full_cfd_resonance_run]]) — true Pareto DE
- [ ] Unsteady CFD + Helmholtz FSI: forced response amplitude, fatigue — currently OUT OF SCOPE

## Reference

- PROGRESS §Phase 4 (deferred checklist, 5 items)
- Dashboard "Optional / Long-term" (NSGA-II, unsteady FSI)
- HANDOFF §5 (wet modes real Laplace pending fluid mesh)

## Context from obsidian_eigenfrequencies.md

### Quick Status (deferred)

| Component | Status | Last Test | Notes |
|-----------|--------|-----------|-------|
| **Wet added-mass (real Laplace)** | 🔴 Open | — | `rayleigh_ratios` NotImplementedError stub |
| **Kinematic blade-passing band** | 🔴 Open | — | Move forbidden band from fixed [100,150] Hz to `Z_guidevanes · n` (auto-derive) |
| **True Pareto optimization** | 🔴 Open | — | NSGA-II if scalarization limiting |
| **Unsteady CFD + Helmholtz FSI** | 🔴 Open | — | Full fluid–structure interaction — out of current scope |

### Open Tasks

- [ ] **P1 vs P2 convergence** `priority::medium`
  - P2 (`SolverConfig.element_degree=2`) more accurate, ~1M DOFs → OOM on <8 GB hosts
  - Test on cluster node (more memory); compare frequencies against P1 baseline

- [ ] **`rayleigh_ratios` (Laplace solve)** `priority::medium`
  - Per-mode added-mass ratio via dolfinx Laplace solve on fluid domain
  - Replace `placeholder_ratios` in `added_mass.py`; see HANDOFF.md

- [ ] **Kinematic blade-passing band** `priority::medium`
  - Move forbidden band from fixed [100,150] Hz to `Z_guidevanes · n` (auto-derive)
  - Update `OptimizationConfig.f_min / f_max` dynamically

- [ ] **True Pareto optimization** `priority::low`
  - NSGA-II if scalarization (`tanh` single-objective) proves limiting
  - Requires multi-objective solver library (pymoo, DEAP)

- [ ] **Unsteady CFD + Helmholtz FSI** `priority::low`
  - Full fluid–structure interaction (forced response amplitude, fatigue)
  - Out of current scope; see documentation.md §6

### Known Problems

1. **`rayleigh_ratios` NotImplementedError** — `added_mass.py` stub. Wet frequencies use placeholder ratio ~15 % shift. Real Laplace solve needs dolfinx fluid mesh + wetted-surface tagging.

### Physical Assumptions & Limitations

| Effect | Impact on Frequencies | Status | Notes |
|--------|----------------------|--------|-------|
| **Added mass (water)** | ↓ 15–40 % (effective mass increases) | 🔴 `added_mass.py` = placeholder (15 % fixed) | Real Laplace solve needs fluid mesh + wetted-surface tagging |
| **Centrifugal stiffening** | ↑ (rotation tensions structure) | 🔴 Not implemented | Small at 90 rpm, significant at 500 rpm |
| **Coriolis coupling** | Modifies mode shapes, splits degenerate modes | 🔴 Not implemented | Only relevant for rotating reference frame |
| **Structural damping** | Reduces resonance amplitude (peak flattening) | 🔴 Not implemented | Hydrodynamic damping from water is significant |
| **Gravity / pressure prestress** | Geometric stiffening from static loads | 🔴 Not implemented | Requires nonlinear static solve first |
| **Hydrodynamic eigenfrequencies** | Water has its own modes, couples with structure | 🔴 Not implemented | Full FSI (Helmholtz) — out of scope |

**Consequence:** The optimizer currently shifts **dry modes** out of the forbidden band. Wet modes (real operating condition) will be **lower** due to added mass. A dry mode at 25.6 Hz becomes ~20–22 Hz in water — this must be accounted for when setting the forbidden band.
