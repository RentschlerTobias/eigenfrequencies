# Graph Report - .  (2026-06-24)

## Corpus Check
- Corpus is ~16,550 words - fits in a single context window. You may not need a graph.

## Summary
- 287 nodes · 405 edges · 22 communities (18 shown, 4 thin omitted)
- Extraction: 84% EXTRACTED · 16% INFERRED · 0% AMBIGUOUS · INFERRED: 66 edges (avg confidence: 0.75)
- Token cost: 46,856 input · 0 output

## Community Hubs (Navigation)
- [[_COMMUNITY_Beam Solver & TUI|Beam Solver & TUI]]
- [[_COMMUNITY_Runner Pipeline Orchestration|Runner Pipeline Orchestration]]
- [[_COMMUNITY_Beam Spline Optimization|Beam Spline Optimization]]
- [[_COMMUNITY_Beam FEM Validation & Euler|Beam FEM Validation & Euler]]
- [[_COMMUNITY_Docs & Eigenvalue Theory|Docs & Eigenvalue Theory]]
- [[_COMMUNITY_Runner Config & Multi-Objective|Runner Config & Multi-Objective]]
- [[_COMMUNITY_Resonance Objective & Optimizer|Resonance Objective & Optimizer]]
- [[_COMMUNITY_Cluster Handoff & Design Notes|Cluster Handoff & Design Notes]]
- [[_COMMUNITY_Runner Modal Solver|Runner Modal Solver]]
- [[_COMMUNITY_Added Mass  Wet Modes|Added Mass / Wet Modes]]
- [[_COMMUNITY_XDMF IO|XDMF IO]]
- [[_COMMUNITY_CFD Evaluation|CFD Evaluation]]
- [[_COMMUNITY_Cluster SLURM Submit|Cluster SLURM Submit]]
- [[_COMMUNITY_Container Build Script|Container Build Script]]
- [[_COMMUNITY_Container Run Script|Container Run Script]]
- [[_COMMUNITY_Src Package Init|Src Package Init]]
- [[_COMMUNITY_Eigenfrequencies Package|Eigenfrequencies Package]]

## God Nodes (most connected - your core abstractions)
1. `BeamConfig` - 23 edges
2. `ModalSolver` - 18 edges
3. `BeamTUI` - 12 edges
4. `RunnerModalSolver` - 12 edges
5. `evaluate_objective()` - 11 edges
6. `optimize_spline_beam()` - 11 edges
7. `main()` - 8 edges
8. `generate_mesh()` - 8 edges
9. `generate_spline_mesh()` - 8 edges
10. `TUIConfig` - 8 edges

## Surprising Connections (you probably didn't know these)
- `Three stages, two containers architecture` --semantically_similar_to--> `Two disjoint software stacks per evaluation`  [INFERRED] [semantically similar]
  turbine_runner/README.md → cluster/env_notes.md
- `RunnerModalSolver` --uses--> `SolverConfig`  [INFERRED]
  turbine_runner/solver.py → demo/beam/config.py
- `main()` --calls--> `DesignConfig`  [INFERRED]
  turbine_runner/optimize.py → turbine_runner/config.py
- `CI docs job (Sphinx, GitHub Pages)` --references--> `Eigenfrequencies Framework docs index`  [INFERRED]
  .github/workflows/ci.yml → docs/source/index.rst
- `CI docker-build job (fenicsx.Dockerfile)` --references--> `Technology stack (gmsh, FEniCSx+SLEPc, pygmo, Sphinx)`  [INFERRED]
  .github/workflows/ci.yml → docs/source/plan.md

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **dtOO geometry to eigenfrequency optimization pipeline** — turbine_runner_dtoo_export, turbine_runner_mesh_prep, turbine_runner_solver, turbine_runner_main, turbine_runner_optimize [EXTRACTED 1.00]
- **FEM generalized eigenvalue formulation (K, M, shape functions, weak form)** — theory_eigenvalues_generalized_eigenproblem, theory_eigenvalues_stiffness_matrix, theory_eigenvalues_mass_matrix, theory_eigenvalues_shape_functions, theory_eigenvalues_weak_formulation [EXTRACTED 1.00]
- **Two-stack cluster integration (dtOO+OpenFOAM vs FEniCSx, backend switch)** — env_notes_dtoo_openfoam_stack, env_notes_fenicsx_dolfinx_stack, env_notes_disjoint_stacks, handoff_runner_backend_switch [EXTRACTED 1.00]

## Communities (22 total, 4 thin omitted)

### Community 0 - "Beam Solver & TUI"
Cohesion: 0.07
Nodes (30): App, OptimizationConfig, OutputConfig, Beam configuration parameters for modal analysis., Configuration for the modal solver.      Attributes:         freq_min: Minimum f, Configuration for optimization.      Attributes:         f_min: Lower frequency, Configuration for output options.      Attributes:         save_vtk: Save result, SolverConfig (+22 more)

### Community 1 - "Runner Pipeline Orchestration"
Cohesion: 0.08
Nodes (31): BCConfig, MaterialConfig, MeshConfig, Runner material properties.      Defaults are structural steel. Unlike the beam, Coordinate-region clamp at the runner hub.      The runner is fixed where it con, Mesh input and volume-meshing fallback options.      Attributes:         msh_pat, _load_design(), main() (+23 more)

### Community 2 - "Beam Spline Optimization"
Cohesion: 0.09
Nodes (29): main(), Spline Beam Optimization Demo  Optimizes a 3-point spline beam to avoid a forbid, Run spline beam optimization demo., BeamConfig, Configuration for spline beam control points.      Attributes:         x1: Middl, Configuration for a rectangular beam.      Attributes:         length: Beam leng, SplineConfig, create_spline_beam() (+21 more)

### Community 3 - "Beam FEM Validation & Euler"
Cohesion: 0.08
Nodes (26): classify_mode(), main(), plot_mode_shape(), plotly_dashboard(), Cantilever beam validation test.  Compares 3D FEM eigenfrequencies with analytic, Legacy 2D plot (deprecated). Use plotly_dashboard instead., Create interactive 3D Plotly dashboard.      Simple, no animation, no play/pause, Classify vibration mode based on displacement pattern.          Args:         ei (+18 more)

### Community 4 - "Docs & Eigenvalue Theory"
Cohesion: 0.11
Nodes (22): Beam Geometry Documentation, create_rectangular_beam(), generate_mesh(), End-refinement mesh strategy (stress concentration), set_mesh_resolution(), ModalSolver API doc, Eigenfrequencies Framework docs index, Project Plan (5 phases) (+14 more)

### Community 5 - "Runner Config & Multi-Objective"
Cohesion: 0.09
Nodes (17): CFDConfig, DesignConfig, ObjectiveConfig, OptimizationConfig, OutputConfig, Configuration for hydraulic turbine runner modal analysis.  Mirrors the dataclas, dtOO design parameters exposed to the optimizer.      `params` maps a dtOO const, Resonance-avoidance optimization settings.      Penalty pushes every eigenfreque (+9 more)

### Community 6 - "Resonance Objective & Optimizer"
Cohesion: 0.12
Nodes (18): cfd_scalar(), combined_objective(), Combined CFD + resonance objective for the multi-objective runner optimization., Scalarize the three hydraulic objectives into one (lower = better).      Args:, Resonance penalty as a constraint term (0 unless a mode is in the band)., Full objective = hydraulic scalar + resonance constraint term.      Returns:, resonance_term(), band_report() (+10 more)

### Community 7 - "Cluster Handoff & Design Notes"
Cohesion: 0.16
Nodes (17): Added mass / wet modes (20-40% frequency drop), Kinematic blade-passing excitation (Z_guidevanes·n), FSI Helmholtz-acoustic ↔ elasticity coupling (deferred), Project Documentation — Eigenfrequency Shape-Optimization Objective, Resonance penalty as constraint objective, tanh scalarized combined objective, bwUniCluster 3.0 Environment Notes, Two disjoint software stacks per evaluation (+9 more)

### Community 8 - "Runner Modal Solver"
Cohesion: 0.20
Nodes (8): Warn if the lowest modes look like rigid-body modes (failed clamp)., Convert eigenvalues to frequencies in Hz., Dry-vs-wet (added-mass) frequency comparison (decision (b), DEFERRED)., Modal analysis of a runner volume mesh with a hub clamp., Build the hub-clamp coordinate predicate from BCConfig., Clamp the hub region; verify a non-empty, plausible clamp., Assemble and solve the generalized eigenproblem (sparse throughout)., RunnerModalSolver

### Community 9 - "Added Mass / Wet Modes"
Cohesion: 0.27
Nodes (9): compare(), placeholder_ratios(), Wet (added-mass) eigenfrequencies — DEFERRED extension, interface + level-1 mode, Wet frequencies from dry frequencies and per-mode added-mass ratios m_a/m_s., Stand-in added-mass ratios until the Laplace solve lands.      Uses a single con, Per-mode added-mass ratio via the level-1 Laplace solve. NOT YET IMPLEMENTED., Return dry and wet frequencies side by side (decision (b) comparison).      Fall, rayleigh_ratios() (+1 more)

### Community 10 - "XDMF IO"
Cohesion: 0.25
Nodes (7): mesh_to_xdmf(), XDMF IO utilities for mesh and results handling., Convert mesh file to XDMF format.      Args:         mesh_file: Path to mesh fil, Read mesh from XDMF file using dolfinx.      Args:         xdmf_file: Path to XD, Write modal analysis results to XDMF file.      Args:         frequencies: Array, read_xdmf_mesh(), write_results_xdmf()

### Community 11 - "CFD Evaluation"
Cohesion: 0.36
Nodes (7): evaluate_cfd(), _last_data_row(), Read steady-CFD hydraulic objectives from an OpenFOAM case (efficiency, cavitati, Return the numeric fields of the last non-comment line of an OpenFOAM .dat., Read a single scalar functionObject result (time in col 0, value in col)., Compute {eta, vcav, dH, P, Q, ok} from an OpenFOAM postProcessing tree.      Arg, _scalar()

### Community 12 - "Cluster SLURM Submit"
Cohesion: 0.40
Nodes (4): FENICSX_SIF, FOAM_SIGFPE, OSLO_LOCK_PATH, submit.sh script

## Knowledge Gaps
- **12 isolated node(s):** `submit.sh script`, `OSLO_LOCK_PATH`, `FOAM_SIGFPE`, `FENICSX_SIF`, `eigenfrequencies` (+7 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **4 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `RunnerModalSolver` connect `Runner Modal Solver` to `Beam Solver & TUI`, `Runner Pipeline Orchestration`, `Docs & Eigenvalue Theory`?**
  _High betweenness centrality (0.428) - this node is a cross-community bridge._
- **Why does `SolverConfig` connect `Beam Solver & TUI` to `Runner Modal Solver`?**
  _High betweenness centrality (0.244) - this node is a cross-community bridge._
- **Why does `ModalSolver` connect `Beam Solver & TUI` to `Beam Spline Optimization`, `Beam FEM Validation & Euler`?**
  _High betweenness centrality (0.172) - this node is a cross-community bridge._
- **Are the 6 inferred relationships involving `BeamConfig` (e.g. with `main()` and `main()`) actually correct?**
  _`BeamConfig` has 6 INFERRED edges - model-reasoned connections that need verification._
- **Are the 10 inferred relationships involving `ModalSolver` (e.g. with `main()` and `main()`) actually correct?**
  _`ModalSolver` has 10 INFERRED edges - model-reasoned connections that need verification._
- **Are the 4 inferred relationships involving `BeamTUI` (e.g. with `BeamConfig` and `OutputConfig`) actually correct?**
  _`BeamTUI` has 4 INFERRED edges - model-reasoned connections that need verification._
- **Are the 3 inferred relationships involving `RunnerModalSolver` (e.g. with `evaluate()` and `main()`) actually correct?**
  _`RunnerModalSolver` has 3 INFERRED edges - model-reasoned connections that need verification._