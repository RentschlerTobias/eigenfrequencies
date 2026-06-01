# Graph Report - /home/t1dde/Work/repos/eigenfrequencies  (2026-05-20)

## Corpus Check
- 20 files · ~7,537 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 92 nodes · 104 edges · 17 communities (13 shown, 4 thin omitted)
- Extraction: 82% EXTRACTED · 18% INFERRED · 0% AMBIGUOUS · INFERRED: 19 edges (avg confidence: 0.78)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- [[_COMMUNITY_Beam Configuration Parameters|Beam Configuration Parameters]]
- [[_COMMUNITY_Modal Solver Core|Modal Solver Core]]
- [[_COMMUNITY_Config & Mesh Creation|Config & Mesh Creation]]
- [[_COMMUNITY_Beam Geometry Generation|Beam Geometry Generation]]
- [[_COMMUNITY_Eigenfrequency Concepts|Eigenfrequency Concepts]]
- [[_COMMUNITY_XDMF IO Utilities|XDMF IO Utilities]]
- [[_COMMUNITY_Boundary Conditions & SLEPc|Boundary Conditions & SLEPc]]
- [[_COMMUNITY_Community 7|Community 7]]
- [[_COMMUNITY_Community 14|Community 14]]
- [[_COMMUNITY_Community 15|Community 15]]
- [[_COMMUNITY_Community 16|Community 16]]

## God Nodes (most connected - your core abstractions)
1. `ModalSolver` - 12 edges
2. `main()` - 8 edges
3. `Generalized Eigenvalue Problem` - 7 edges
4. `generate_mesh()` - 6 edges
5. `BeamConfig` - 6 edges
6. `ModalSolver` - 6 edges
7. `solve` - 6 edges
8. `generate_mesh` - 5 edges
9. `Stiffness Matrix` - 5 edges
10. `BeamConfig` - 4 edges

## Surprising Connections (you probably didn't know these)
- `analytical_frequencies` --conceptually_related_to--> `Euler-Bernoulli Beam Theory`  [INFERRED]
  demo/beam/main.py → docs/source/theory/eigenvalues.md
- `solve` --calls--> `SLEPc`  [EXTRACTED]
  demo/beam/solver.py → docs/source/plan.md
- `solve` --calls--> `FEniCSx`  [EXTRACTED]
  demo/beam/solver.py → docs/source/plan.md
- `Lagrange P2 Elements` --references--> `solve`  [EXTRACTED]
  docs/source/plan.md → demo/beam/solver.py
- `compute_frequencies` --conceptually_related_to--> `Eigenfrequency`  [INFERRED]
  demo/beam/solver.py → docs/source/theory/eigenvalues.md

## Hyperedges (group relationships)
- **Beam Analysis Pipeline** — demo_beam_config, demo_beam_geometry_generatemesh, demo_beam_solver_modalsolver, demo_beam_main_analyticalfreqs, demo_beam_main [EXTRACTED 1.00]
- **Eigenvalue Theory Concepts** — generalized_eigenvalue_problem, stiffness_matrix, mass_matrix, eigenfrequency, weak_formulation, shape_functions [EXTRACTED 1.00]
- **IO Operations** — src_io_meshtoxdmf, src_io_readxdmfmesh, src_io_writeresultsxdmf, xdmf_format [INFERRED 0.85]

## Communities (17 total, 4 thin omitted)

### Community 0 - "Beam Configuration Parameters"
Cohesion: 0.14
Nodes (12): BeamConfig, OutputConfig, Beam configuration parameters for modal analysis., Configuration for the modal solver.      Attributes:         freq_min: Minimum f, Configuration for output options.      Attributes:         save_vtk: Save result, Configuration for a rectangular beam.      Attributes:         length: Beam leng, SolverConfig, analytical_frequencies() (+4 more)

### Community 1 - "Modal Solver Core"
Cohesion: 0.15
Nodes (8): ModalSolver, FEniCSx modal analysis solver for eigenfrequency computation., Convert eigenvalues to frequencies in Hz., Save results to files., Modal analysis solver using FEniCSx and SLEPc., Load mesh from Gmsh .msh file., Apply clamped boundary condition at x=0., Solve the modal analysis problem.          Returns:             Tuple of (eigenv

### Community 2 - "Config & Mesh Creation"
Cohesion: 0.19
Nodes (13): BeamConfig, OutputConfig, SolverConfig, create_rectangular_beam, generate_mesh, set_mesh_resolution, Beam Demo Main, analytical_frequencies (+5 more)

### Community 3 - "Beam Geometry Generation"
Cohesion: 0.24
Nodes (10): beam_to_xdmf(), create_rectangular_beam(), generate_mesh(), Beam geometry generation using gmsh., Convert gmsh mesh to XDMF format for FEniCSx.      Args:         config: Beam co, Create a rectangular beam geometry.      Args:         config: Beam configuratio, Set mesh resolution for the beam geometry., Generate beam mesh and save to XDMF format.      Args:         config: Beam conf (+2 more)

### Community 4 - "Eigenfrequency Concepts"
Cohesion: 0.27
Nodes (11): compute_frequencies, Eigenfrequency, Euler-Bernoulli Beam Theory, FEniCSx, Generalized Eigenvalue Problem, Mass Matrix, Modal Analysis, pygmo (+3 more)

### Community 5 - "XDMF IO Utilities"
Cohesion: 0.25
Nodes (7): mesh_to_xdmf(), XDMF IO utilities for mesh and results handling., Convert mesh file to XDMF format.      Args:         mesh_file: Path to mesh fil, Read mesh from XDMF file using dolfinx.      Args:         xdmf_file: Path to XD, Write modal analysis results to XDMF file.      Args:         frequencies: Array, read_xdmf_mesh(), write_results_xdmf()

### Community 6 - "Boundary Conditions & SLEPc"
Cohesion: 0.33
Nodes (6): Clamped Boundary Condition, apply_clamped_bc, create_mesh, solve, Lagrange P2 Elements, SLEPc

## Knowledge Gaps
- **11 isolated node(s):** `Sphinx Configuration`, `SolverConfig`, `OutputConfig`, `beam_to_xdmf`, `mesh_to_xdmf` (+6 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **4 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `main()` connect `Beam Configuration Parameters` to `Modal Solver Core`, `Beam Geometry Generation`?**
  _High betweenness centrality (0.344) - this node is a cross-community bridge._
- **Why does `generate_mesh()` connect `Beam Geometry Generation` to `Beam Configuration Parameters`?**
  _High betweenness centrality (0.324) - this node is a cross-community bridge._
- **Why does `gmsh` connect `Beam Geometry Generation` to `Config & Mesh Creation`, `Eigenfrequency Concepts`?**
  _High betweenness centrality (0.320) - this node is a cross-community bridge._
- **Are the 4 inferred relationships involving `ModalSolver` (e.g. with `BeamConfig` and `SolverConfig`) actually correct?**
  _`ModalSolver` has 4 INFERRED edges - model-reasoned connections that need verification._
- **Are the 5 inferred relationships involving `main()` (e.g. with `BeamConfig` and `SolverConfig`) actually correct?**
  _`main()` has 5 INFERRED edges - model-reasoned connections that need verification._
- **Are the 2 inferred relationships involving `Generalized Eigenvalue Problem` (e.g. with `SLEPc` and `compute_frequencies`) actually correct?**
  _`Generalized Eigenvalue Problem` has 2 INFERRED edges - model-reasoned connections that need verification._
- **What connects `Beam configuration parameters for modal analysis.`, `Configuration for a rectangular beam.      Attributes:         length: Beam leng`, `Configuration for the modal solver.      Attributes:         freq_min: Minimum f` to the rest of the system?**
  _36 weakly-connected nodes found - possible documentation gaps or missing edges._