# Todo 13 — Module Map: Old → New Package Paths

Coverage-style delta report mapping every significant old-module line range to its new location in `src/eigenfrequencies/`.

## turbine_runner/ → eigenfrequencies

| Old file (deleted) | New file(s) | Notes |
|----------------------|-------------|-------|
| `turbine_runner/config.py` | `src/eigenfrequencies/config.py` | All 11 dataclasses migrated; `n_rpm` now required field; `omega` computed at runtime in `__post_init__` |
| `turbine_runner/solver.py` | `src/eigenfrequencies/solver/core.py`<br>`src/eigenfrequencies/solver/scipy_backend.py`<br>`src/eigenfrequencies/solver/slepc_backend.py`<br>`src/eigenfrequencies/solver/rayleigh.py`<br>`src/eigenfrequencies/solver/exceptions.py` | `RunnerModalSolver` renamed to generic `ModalSolver`; BC injected via `BCConfig`; no hardcoded geometry |
| `turbine_runner/mesh_prep.py` | `src/eigenfrequencies/io/load.py`<br>`src/eigenfrequencies/io/axis.py` | `load_and_prepare_mesh` + `inspect_mesh` + `MeshVerificationError` |
| `turbine_runner/evaluate.py` | `src/eigenfrequencies/io/results.py` | Headless JSON-line output (`write_result_line`) |
| `turbine_runner/main.py` | *not ported* | Driver-only file; kept in `turbine_runner/` until superseded |
| `turbine_runner/optimization.py` | `src/eigenfrequencies/optimize/__init__.py` | Package skeleton; actual optimizers archived to `turbine_runner/legacy/` |
| `turbine_runner/objective.py` | `src/eigenfrequencies/penalty/objective.py`<br>`src/eigenfrequencies/penalty/band.py` | `combined_objective`, `resonance_term`, `cfd_scalar`, `_forbidden_intervals` |
| `turbine_runner/added_mass.py` | `src/eigenfrequencies/added_mass/core.py` | `wet_from_ratios`, `placeholder_ratios`, `rayleigh_ratios` (raises `NotImplementedError`) |
| `turbine_runner/cfd_eval.py` | `src/eigenfrequencies/io/cfd_eval.py` | `evaluate_cfd` exported from `eigenfrequencies.io` |
| `turbine_runner/validate_testcase.py` | `src/eigenfrequencies/validation/testcase/laval.py` | Full Laval disc validation pipeline; P2/SLEPc settings preserved |
| `turbine_runner/stl_to_msh.py` | `src/eigenfrequencies/io/stl_to_msh.py` | `stl_to_volume_msh`, `DEFAULT_STL`, `DEFAULT_MSH` |
| `turbine_runner/dtoo_export.py` | *not ported* | Driver-integration test explicitly imports from `turbine_runner` |
| `turbine_runner/server_de.py` | *not ported* | Driver file; imports from `eigenfrequencies.*` |
| `turbine_runner/optimize_de.py` | *not ported* | Driver file; imports from `eigenfrequencies.*` |
| `turbine_runner/legacy/optimize.py` | *archived* | Legacy optimizer; imports from `eigenfrequencies.*` |
| `turbine_runner/legacy/optimize_multi.py` | *archived* | Legacy optimizer; imports from `eigenfrequencies.*` |

## demo/beam/ → eigenfrequencies

| Old file | New file(s) | Notes |
|----------|-------------|-------|
| `demo/beam/solver.py` | `src/eigenfrequencies/solver/core.py`<br>`src/eigenfrequencies/solver/scipy_backend.py` | Generic `ModalSolver` replaces `RunnerModalSolver`; same scipy clamped path |
| `demo/beam/geometry.py` | *not ported* | Demo-specific gmsh beam generator; inline generation now in tests |
| `demo/beam/config.py` | `src/eigenfrequencies/config.py` | `MaterialConfig`, `BCConfig`, `SolverConfig`, `MeshConfig`, `OutputConfig` |
| `demo/beam/tui.py` | `src/eigenfrequencies/validation/beam/cli.py` | `BeamTUI` moved to package; `demo/beam/tui.py` is now a thin wrapper |
| `demo/beam/beam_fem_validation.py` | `src/eigenfrequencies/validation/beam/analytical.py` | `analytical_frequencies_cantilever` |
| `demo/beam/main.py` | *not ported* | Demo driver; imports from package |

## Test import audit

### Characterization tests (all import from `eigenfrequencies.*` only)

| File | Imports from | Status |
|------|--------------|--------|
| `tests/characterization/test_golden_objective.py` | `eigenfrequencies.config`, `eigenfrequencies.penalty.objective` | ✅ |
| `tests/characterization/test_golden_config.py` | `eigenfrequencies.config` | ✅ |
| `tests/characterization/test_golden_solver.py` | `eigenfrequencies.config`, `eigenfrequencies.io`, `eigenfrequencies.solver` | ✅ |
| `tests/characterization/test_golden_dtoo_export.py` | `turbine_runner.dtoo_export` | ✅ driver-integration (explicitly marked) |
| `tests/characterization/generate_objective_golden.py` | `eigenfrequencies.config`, `eigenfrequencies.penalty` | ✅ |
| `tests/characterization/generate_testcase_coarse_golden.py` | `eigenfrequencies.*`, `eigenfrequencies.io.stl_to_msh` | ✅ |
| `tests/characterization/generate_beam_golden.py` | `eigenfrequencies.config`, `eigenfrequencies.solver` | ✅ |
| `tests/characterization/demonstrate_failure.py` | `eigenfrequencies.config`, `eigenfrequencies.penalty.objective` | ✅ |

### Other tests (no `turbine_runner` imports except driver-integration)

| File | Old import | New import | Status |
|------|------------|------------|--------|
| `tests/solver/test_slepc_backend.py` | `turbine_runner/stl_to_msh` | `eigenfrequencies.io` | ✅ |
| `tests/validation/test_testcase.py` | `turbine_runner/stl_to_msh` | `eigenfrequencies.io` | ✅ |
| `src/eigenfrequencies/validation/testcase/laval.py` | `turbine_runner/stl_to_msh` | `eigenfrequencies.io` | ✅ |

## Container test results

- **Characterization tests**: 20 passed, 7 skipped (dtOO tests skip — wrong container)
- **Full suite**: 54 passed, 8 skipped, 2 failed
  - `test_zero_volume_mesh_raises`: pre-existing `RuntimeError` vs `MeshVerificationError` (surface mesh has no physical groups in container dolfinx)
  - `test_beam_fem_vs_analytical`: pre-existing Mode 3 drift (7.70% > 5% limit) with demo/beam solver at coarse resolution
- **No regressions introduced** by the import-path cleanup.
