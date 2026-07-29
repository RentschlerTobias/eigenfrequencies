# Learnings — eigenfrequencies-final-design

Conventions, patterns, and successful approaches discovered during work on this plan.

_Auto-scaffolded by /start-work. Append new entries below - never overwrite._

---

## Todo 3 — Golden objective characterization

**What was built:**
- `tests/characterization/test_golden_objective.py` — pytest test that replays `resonance_term`, `cfd_scalar`, and `combined_objective` against frozen values from `de_history_resonance_only.jsonl` (gen 0, rows 0-4) and `de_history_combined.jsonl` (CFD scalars).
- `tests/characterization/golden/objective_cases.json` — frozen replay outputs documenting source row, design preset, band bounds, inputs, and all three function outputs.
- `tests/characterization/generate_objective_golden.py` — script to regenerate the golden JSON if the canonical source or config defaults change.

**Key findings:**
1. The `de_history_resonance_only.jsonl` schema has `f_resonance` and `f1` (single frequency), while `de_history_combined.jsonl` has `f_cfd`, `eta`, `vcav`, `dH`. The two files must be paired by row index for a complete replay.
2. `f1` values in gen 0-4: 25.84, 25.84, 25.84, 26.84, 28.53 Hz. The first three fall inside the first forbidden band [16.6, 26.6] and incur a non-zero resonance penalty (~0.764). The last two are outside all bands (penalty = 0.0).
3. The CFD scalar for all five rows is identical (2.471488507558198) because the combined.jsonl rows 0-4 happen to share the same CFD result — this is expected when the DE population hasn't yet explored new designs.
4. `N_RPM=72` must be set in the environment **before** any import of `turbine_runner.config` to bypass the import-time `templateState.xml` read. This is the same workaround used in `test_golden_config.py`.
5. Relative tolerance 1e-9 is sufficient and strict — the replay uses the exact same Python/numpy math as the original run, so bit-exact equality is achievable for scalar outputs. The `_rel_close` helper handles the zero case explicitly.
6. Failure path: narrowing `margin_hz` by 1.0 Hz changes the first forbidden band to [17.6, 25.6], which excludes the 25.84 Hz mode. The resonance penalty drops from 0.764 to 0.0, and the combined total drops from 3.235 to 2.471. This confirms the golden test would catch any band-bound regression.

**Evidence:**
- `todo-3-happy.log`: 6 passed (5 parametrized replay cases + 1 perturbed-bound divergence test)
- `todo-3-failure.log`: perturbed `margin_hz` produces different `resonance_term` (0.764 → 0.0) and `combined_objective` total (3.235 → 2.471)

## Todo 4 — dtOO export characterization (2026-07-28)

### dtOO is NOT available locally
- `dtOOPythonSWIG` import fails with `ModuleNotFoundError` in the local environment.
- The test module uses `pytestmark = pytest.mark.skipif(...)` at module level so
  all tests skip gracefully with a clear message when dtOO is unavailable.
- The skip reason explicitly tells the user to run inside the dtOO container:
  `atismer/dtoo-opensuse:stable` with `LD_LIBRARY_PATH` set.

### Env-override matrix in golden/dtoo_export.json
- `DTOO_CASE_DIR`: default `~/dtOO/build/test/tistos`; nonexistent dir raises
  `FileNotFoundError` at `os.chdir()` in `main()` — this is the frozen error type.
- `DTOO_DESIGN_JSON`: default `""` (empty); invalid path falls back to baseline
  geometry with a console message.
- `DTOO_OUTPUT_MSH`: default `data/runner.msh`; parent dirs created via
  `os.makedirs(exist_ok=True)`.
- `DTOO_LOG_FILE`: default `<dirname(DTOO_OUTPUT_MSH)>/dtoo_build.log`.
- `DTOO_MACHINE_XML`, `DTOO_STATE_XML`, `DTOO_STATE`, `DTOO_MECH_VOLUME`,
  `DTOO_ADJUST_PLUGIN`: all have sensible defaults documented in the golden JSON.

### Test structure
- `TestDtOOExportHappyPath`: verifies export produces runner.msh, checksum matches
  golden (xfail when checksum is TBD), and design.json roundtrip alters the mesh.
- `TestDtOOExportEnvOverrides`: verifies env-override behaviors including the
  frozen error type for nonexistent case dir.
- The golden checksum is `"TBD — generate in dtOO container"`; the first
  container run will xfail and print the actual SHA-256 for manual update.

### Evidence files
- `todo-4-happy.log`: pytest output showing 7 skipped tests with clear message.
- `todo-4-failure.log`: pytest output + documentation of expected FileNotFoundError
  when DTOO_CASE_DIR points at a nonexistent directory.

## Todo 2 — Golden solver characterization (2026-07-28)

### What was built
- `tests/characterization/test_golden_solver.py` — pytest test with two parametrized
  solver checks:
  1. `test_beam_golden`: cantilever beam (demo/beam) vs `golden/beam.json`
  2. `test_testcase_coarse_golden`: free-free Laval disc coarse mesh
     (turbine_runner) vs `golden/testcase_coarse.json`
- `tests/characterization/golden/testcase_coarse.json` — moved from
  `tests/characterization/testcase_coarse.json` (29 MB).

### Key findings
1. **Import path collision**: both `demo/beam/` and `turbine_runner/` contain
   `config.py`, `solver.py`, etc.  The test uses `sys.path.insert` + normal
   `import` for the first set, then deletes the conflicting modules from
   `sys.modules` and repeats for the second set.  This lets `solver.py`'s
   internal `from config import …` resolve to the correct file each time.
2. **N_RPM=72 workaround**: must be set in `os.environ` **before** any import
   of `turbine_runner.config` to bypass the import-time `templateState.xml`
   read.  Same pattern as Todo 5 / `test_golden_config.py`.
3. **Free-free rigid-mode removal**: the testcase solver returns 16 eigenpairs;
   6 are rigid-body modes (< 1 Hz).  The test drops those and compares only the
   first 10 elastic modes, matching the generator script.
4. **MAC computation**: displacement-norm vectors per node are extracted from
   the eigenvector DOFs and compared via the standard Modal Assurance Criterion
   formula.  MAC ≥ 0.999 guarantees the mode shape hasn't drifted.
5. **Frequency tolerance**: relative error ≤ 1e-4 is tight enough to catch solver
   regressions but loose enough to survive harmless platform noise.
6. **pytest 9 + conftest conflict**: the container has pytest 9.0.3 without
   `pytest-xdist`.  `tests/conftest.py` tried to register a fallback `-n`
   option, but pytest 9 reserves lowercase short options.  Removing the `-n`
  short option from the fallback fixes the crash.  Tests are run with
   `-o addopts=` to disable the `-n auto` from `pyproject.toml` inside the
   container.
7. **Failure path**: hand-editing beam mode 1 frequency from 8.394550 Hz to
   +5 % (8.814278 Hz) makes the test fail with a clear message naming the
   drifting mode:
   `Beam mode 1 frequency drift: computed=8.394550 Hz, expected=8.814278 Hz, rel_err=4.761905e-02`.

### Evidence files
- `todo-2-happy.log`: 2 passed (beam + testcase_coarse) in ~46 s.
- `todo-2-failure.log`: 1 failed — beam mode 1 frequency drift detected after
  +5 % hand-edit, then reverted to original golden value.

## Todo 7 — Package skeleton and config dataclass migration (2026-07-28)

### What was built
- `src/eigenfrequencies/` package skeleton with 10 subpackages:
  `io/`, `solver/`, `bc/`, `materials/`, `penalty/`, `added_mass/`, `validation/`,
  `adapters/` (with `adapters/dtoo/`), `optimize/`, `mcp/`.
- Root modules: `config.py`, `provenance.py`, `version.py`, `__init__.py` (public API).
- All 11 dataclasses moved from `turbine_runner/config.py` with two critical fixes.

### Critical fixes
1. **Removed import-time `templateState.xml` read.**
   - Deleted `_load_n_rpm_from_template()` and `_N_RPM_DEFAULT` global.
   - `OptimizationConfig.n_rpm` is now a **required field** (no default).
   - `CFDConfig.n_rpm` is now a **required field** (newly added).
   - The dtOO adapter will supply `n_rpm` at runtime.
2. **`CFDConfig.omega` computed at runtime.**
   - Removed class-definition-time default `2.0 * math.pi * _N_RPM_DEFAULT / 60.0`.
   - `omega` is now `Optional[float] = None`.
   - `__post_init__` computes `self.omega = 2.0 * math.pi * self.n_rpm / 60.0` when not provided.
   - Verified: `CFDConfig(n_rpm=90.0).omega == 9.42477796076938` with `< 1e-12` tolerance.

### Field-order trap in dataclasses
Python dataclasses require non-default arguments to precede default arguments.
The first attempt placed `n_rpm: float` (no default) after `Z_guidevanes: int = 18`
in `OptimizationConfig`, which raised:
`TypeError: non-default argument 'n_rpm' follows default argument 'Z_guidevanes'`.
Fix: reorder fields so required fields come first.

### Path defaults adjusted
`MeshConfig.msh_path` and `OutputConfig.output_dir` previously used
`os.path.join(_HERE, ...)` pointing into `turbine_runner/`. In the new package
there is no `_HERE`, so defaults changed to simple relative strings
(`"data/runner.msh"`, `"output"`).

### Old skeleton cleanup
Deleted `src/geometry/`, `src/optimization/`, `src/solver/`, `src/io/`
(the last had 66 lines of XDMF utilities, unused anywhere in the repo).
Also cleaned `src/eigenfrequencies.egg-info/` build artifact.

### Evidence files
- `todo-7-happy.log`: all 11 dataclasses import OK, clean-env import OK,
  runtime omega derivation OK, `n_rpm` required correctly (TypeError when missing).
- `todo-7-failure.log`: old skeleton packages (`geometry`, `optimization`, `solver`)
  raise `ModuleNotFoundError`; old `src.io` XDMF utilities no longer available.

