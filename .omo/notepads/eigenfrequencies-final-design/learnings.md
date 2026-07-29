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

