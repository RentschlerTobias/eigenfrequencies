# Learnings — eigenfrequencies-final-design

Conventions, patterns, and successful approaches discovered during work on this plan.

_Auto-scaffolded by /start-work. Append new entries below - never overwrite._

---

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

