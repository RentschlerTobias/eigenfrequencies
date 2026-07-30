# eigenfrequencies-final-design - Work Plan

## TL;DR (For humans)

**What you'll get:** The validated FEniCSx modal-analysis code (currently unpackaged in `turbine_runner/`, dry-mode only) becomes `eigenfrequencies`, a standalone, library-first Python package with YAML config + full CLI; a declarative dtOO adapter layer (ships tistos, canadaLight, naca machine YAMLs); an optimizer layer (DE/PSO/CMA-ES/Bayesian-TPE + RL via gymnasium/SB3 + offline-RL) with native island-model parallelization and a transport-agnostic evaluator pool; and a job-based MCP server (fastmcp, stdio) so an LLM can drive solves/validations/optimizations. All work on branch `refactor/standalone-tool`.

**Why this approach:** Library-first packaging means CLI, MCP, and future UIs wrap ONE API. Golden-reference characterization tests (frozen before the move) make the refactor of numerically validated code safe. Declarative per-machine YAMLs make "every dtOO geometry" a config task, not a code task. The island model is implemented natively over an ask/tell protocol — the concepts come from `../de_framework`, but neither pygmo/pagmo nor a hard Pyro5 binding becomes a dependency.

**What it will NOT do:** No wet-mode/FSI implementation (roadmap; the added-mass interface stays a stub with the ~15% placeholder). No NSGA-II (eigenfrequency objective stays a penalty, not a Pareto axis). No ACO, no HippoRAG, no Figma/code-connect/config UI, no PyPI release (dolfinx is not on PyPI), no adoption of the colleague's PBO (SB3-pluggable only), no CFD-coupling rewrite (stays project code), no SLURM-array evaluator backend (Later TODO), no work on `cfd-eigenfreq-multiobjective`, no scope reduction ("MVP").

**Effort:** 42 implementation todos + 4 final-verification tasks, in 8 dependency-ordered waves. Multi-week project scale.

**Risk:** Medium. Numerics are protected by golden-reference tests frozen from the validated state (beam, Laval disc, tistos-coarse; tolerances: eigenfrequency rel. error ≤ 1e-4, mode-shape MAC ≥ 0.999). dtOO-dependent todos need the dtOO docker image (`atismer/dtoo-opensuse:stable`) or the cluster environment (`source ~/pe`). canadaLight's dtOO state (solid/mechanical volume present?) is unknown → dedicated pre-check todo with a documented fallback. The full Laval disc validation needs ~28.6 GB RAM → stays opt-in (`RUN_TESTCASE_VALIDATION=1`), cluster-run evidence acceptable.

**Decisions (approved by user, 2026-07-28; full log in `.omo/drafts/eigenfrequencies-final-design.md`):**
1. Standalone core + optional layers (adapter/optimizer as extras, CFD+cluster stay project code, wet/FSI roadmap).
2. One package `src/eigenfrequencies/`; `turbine_runner/` becomes a thin dtOO project driver.
3. Public repo; conda `environment.yml` + Dockerfile; `uv pip install . --no-deps`; no PyPI.
4. YAML config + typer CLI (solve/validate/optimize/report) + exported JSON Schema; cluster runs = config file + commit hash.
5. Declarative per-machine dtOO adapter YAML (incl. explicit mesh scale factor for the non-physical-units caveat).
6. Ship + validate adapters for tistos, canadaLight, naca.
7. Optimizer ask/tell protocol; backends DE (custom, preserved), PSO (pymoo), CMA-ES (cma), BO/TPE (optuna); ACO rejected; NSGA-II roadmap.
8. RL backend: generic gymnasium.Env over the objective interface, SB3-compatible, offline-RL exporter (`de_history*.jsonl` → d3rlpy), dry-modal first.
9. Job-based MCP server (fastmcp stdio, submit/poll/fetch), thin over the same library API.
10. No config UI (Figma variant researched and rejected; schema-generated form parked).
11. graphify: mandatory `graphify update` post-refactor + corpus ingest; MCP serves NO code-knowledge tools (that is graphify's layer).
12. Validation suite = beam vs Euler-Bernoulli + Laval TestCaseGeomertyMesh vs ANSYS+experiment; tistos is NOT a validation showcase.
13. Characterization-first tests (golden references), tests-after for new modules, agent-executed QA per todo.
14. Native island model + EvaluatorPool (ProcessPool + Pyro5 as one transport); islands default 4 (diversity knob — evaluator worker count comes from SLURM_NTASKS, NOT island count); pytest-xdist; no pygmo/pagmo; SLURM-array evaluator later.
15. All work on new branch `refactor/standalone-tool` off **`main` HEAD** (e6f10cf — validated state incl. STL/Laval validation, de_history, cluster scripts lives on main; the older `cfd-eigenfreq-multiobjective` branch stays untouched as history).

## Scope

**In scope (full request, no reduction):**
- Package refactor: `turbine_runner/` → `src/eigenfrequencies/` (io, solver, bc, materials, penalty, added_mass, validation), thin `turbine_runner/` driver.
- Tool interface: YAML config, JSON Schema export, typer CLI (solve/validate/optimize/report), run provenance (config snapshot + git commit hash).
- dtOO adapter layer: adapter core + machine YAMLs for tistos, canadaLight, naca + scale/axis helper CLIs.
- Optimizer layer: ask/tell protocol, DE/PSO/CMA-ES/BO backends, EvaluatorPool (ProcessPool + Pyro5), native island model, conformance tests.
- RL backend: gymnasium.Env, SB3 smoke (PPO/SAC/TD3), offline-RL exporter (d3rlpy).
- MCP server: job manager, fastmcp tools, resources (results/machines/docs), client config + smoke.
- Knowledge/distribution: graphify update + corpus ingest, environment.yml, pyproject extras, Dockerfile refresh, docs set, public-repo prep.

**Must-NOT-have (guardrails, verified in F4):** wet-mode/FSI implementation; NSGA-II; ACO; HippoRAG; Figma/code-connect/config UI; PyPI release workflow; PBO adoption; MCP code-knowledge tools; CFD-coupling rewrite; pygmo/pagmo dependency; SLURM-array evaluator backend; commits on `cfd-eigenfreq-multiobjective`; any MVP/phase-1 reduction; git history rewrite.

**Out of scope, parked in Later TODO:** dtOO introspection tooling (adapter proposes design params from dtOO constValues/dtLattice); schema-generated web config form (react-jsonschema-form); SLURM-array evaluator backend; wet-mode/FSI; NSGA-II Pareto (only if penalty scalarization proves limiting).

## Verification strategy

- **Characterization-first (Wave 1, before any move):** golden references frozen from the validated state — eigenfrequencies + mode shapes for beam / Laval-disc-coarse / tistos-coarse; penalty/objective values replayed from recorded `de_history*.jsonl` rows; dtOO export checksums; config roundtrip. Tolerances: eigenfrequency rel. error ≤ 1e-4; mode-shape MAC ≥ 0.999; objective values rel. error ≤ 1e-9 (pure function replay). These tests run against the OLD code first (must pass), then against the NEW package after every wave (must stay green).
- **Existing validation suites stay green throughout:** beam vs Euler-Bernoulli (always), Laval disc vs ANSYS+experiment (opt-in `RUN_TESTCASE_VALIDATION=1`; needs ~28.6 GB RAM — cluster or big-RAM machine; skip-with-message otherwise).
- **Tests-after for new modules** (adapters, optimizers, RL, MCP): each todo ships its tests in the same commit.
- **Agent-executed QA per todo:** happy + failure scenario, exact tool + invocation, evidence written to `.omo/evidence/eigenfrequencies-final-design/todo-<N>-<case>.<ext>`. Zero human-intervention verification.
- **Environment for QA (pick first that works, record which in evidence):** (a) local docker `docker run --rm -v "$PWD":/work -w /work eigenfrequencies-fenicsx:latest <cmd>`; (b) conda `conda env create -f environment.yml && conda activate eigenfrequencies && uv pip install . --no-deps`; (c) cluster enroot `pyxis_fenicsx` for SLURM-scale items. dtOO items additionally: `atismer/dtoo-opensuse:stable` container or `source ~/pe` on the cluster.
- **Final verification wave:** F1 plan-compliance audit, F2 code-quality review, F3 real end-to-end QA matrix, F4 scope-fidelity audit — all four must APPROVE before completion is declared.

## Execution strategy

Waves run in order; inside a wave, todos are sequential unless noted. Dependency matrix (X → requires):

| Todo | Requires |
|---|---|
| 1 | — |
| 2–6 | 1 |
| 7 | 2–6 (golden net must exist first) |
| 8–11 | 7 |
| 12 | 8–11 |
| 13 | 2–6, 12 |
| 14–15 | 7 |
| 16–17 | 14 |
| 18 | 16, 17 |
| 19–20 | 8–10 |
| 21 | 19, 4 |
| 22–23 | 19 |
| 24 | 7 |
| 25 | 24 |
| 26 | 25 |
| 27–29 | 24 |
| 30 | 24–29 |
| 31–32 | 24 (objective interface), 14 |
| 33 | 7, 19 |
| 34 | 16–18 |
| 35–36 | 34 |
| 37 | 35, 36 |
| 38 | 12 (final package layout) |
| 39 | 14, 24, 31, 35 (knows all deps) |
| 40 | 39 |
| 41 | 14–18, 19–23, 34–37 (documents real behavior) |
| 42 | 39 |
| F1–F4 | all |

Parallelization notes: waves 5–7 may overlap once wave 3 is done (different modules); wave 4 (dtOO env) can run parallel to wave 3; wave 8 is last. pytest-xdist (`pytest -n auto`) is the default test invocation from todo 6 onward.

## Todos

### Wave 1 — Branch + characterization net

- [x] 1. Create refactor branch
  - **What:** Create branch `refactor/standalone-tool` from the current HEAD of `main` (e6f10cf — validated state incl. kinematic band, Laval STL validation assets, de_history checkpoints, cluster scripts; verified: `cfd-eigenfreq-multiobjective` = d55c1d3 LACKS these). All subsequent todos commit ONLY to this branch. Do not touch `main` or `cfd-eigenfreq-multiobjective`. Do not push.
  - **References:** git repo root; draft decisions #15 (`.omo/drafts/eigenfrequencies-final-design.md`).
 - **Acceptance:** `git branch --show-current` = `refactor/standalone-tool`; `git rev-parse refactor/standalone-tool` == `git rev-parse main`; `git status --porcelain` shows no unexpected modifications.
 - **QA happy:** `git checkout main && git checkout -b refactor/standalone-tool && git branch --show-current` → evidence `todo-1-happy.log`.
  - **QA failure:** run the checkout command a second time → must fail with "already exists"; verify no force-overwrite was used → evidence `todo-1-failure.log`.
  - **Commit:** none (branch creation only; record SHA in evidence).

- [x] 2. Golden references: solver outputs
  - **What:** Create the test layout `tests/{characterization,validation,optimize,rl,mcp,io,config,adapters}/` with pytest markers registered in pyproject: `slow`, `requires_container`, `requires_dtoo`, `requires_slurm`, `serial`. Add `tests/characterization/test_golden_solver.py` + golden data `tests/characterization/golden/{beam,testcase_coarse,tistos_coarse}.json`. Freeze, from the CURRENT code: first 10 eigenfrequencies + reference mode-shape data (displacement-norm vector per mode for MAC) for (a) beam config from `demo/beam/`, (b) Laval disc in a COARSE variant (generate a coarse tet mesh of `TestCaseGeomertyMesh.stl` via the existing mesh path; the full P2/325k-tet/28.6 GB case stays opt-in and is NOT the golden case), (c) tistos runner on its coarsest existing mesh config via `turbine_runner` — this is a **refactor-parity reference, NOT a validation showcase** (decision 12); tistos cases live in the dtOO environment (cluster `~/dtOO/build/test/tistos` or the dtOO container), so mark it `requires_dtoo` and skip-with-reason when unavailable — record skip in evidence and generate this golden file in todo 21 instead. Each JSON stores: frequencies, solver settings, mesh hash, git SHA, and the EXACT source config used (no unnamed defaults).
  - **References:** `turbine_runner/solver.py` (RunnerModalSolver, scipy clamped + SLEPc free-free paths), `turbine_runner/mesh_prep.py`, `demo/beam/beam_fem_validation.py`, `TestCaseGeomertyMesh.stl`, `VALIDATION_summary.md`.
  - **Acceptance:** tests pass against the current (unmoved) code; golden JSONs committed; tolerances encoded in the test: freq rel. ≤ 1e-4, MAC ≥ 0.999.
  - **QA happy:** `docker run --rm -v "$PWD":/work -w /work eigenfrequencies-fenicsx:latest python -m pytest tests/characterization/test_golden_solver.py -q` → pass → evidence `todo-2-happy.log` + golden JSONs.
  - **QA failure:** hand-edit one golden frequency by +5% → rerun → test must FAIL naming the drifting mode → revert → evidence `todo-2-failure.log`.
  - **Commit:** `test(characterization): freeze golden solver references (beam, laval-coarse, tistos-coarse)`

- [x] 3. Golden references: penalty/objective values
  - **What:** Add `tests/characterization/test_golden_objective.py` + `golden/objective_cases.json`. CANONICAL SOURCE (pinned, no ambiguity): `turbine_runner/de_history_resonance_only.jsonl`, generation 0, rows 0–4 (5 rows); record the run's `DESIGN_PRESET` and band bounds alongside (the four `de_history*.jsonl` files have DIFFERENT schemas — resonance_only has `f_resonance`/`f1`, combined has `f_cfd`/`eta`/`vcav`/`dH` — so the golden file documents which schema each case came from). For each row, replay `resonance_term`, `cfd_scalar` (tanh mapping, using the recorded CFD scalars as fixed inputs — no CFD rerun), and `combined_objective`; freeze outputs.
  - **References:** `turbine_runner/objective.py`, `turbine_runner/optimization.py` (forbidden-band penalty; kinematic band Z·n harmonics), `turbine_runner/de_history*.jsonl`.
  - **Acceptance:** replay matches frozen values within rel. 1e-9; JSON documents source row (file + line index) per case.
  - **QA happy:** pytest invocation (same container pattern) → pass → evidence `todo-3-happy.log`.
  - **QA failure:** perturb one penalty band bound in the replay config → replay must produce a DIFFERENT value and the comparison test must fail → evidence `todo-3-failure.log`.
  - **Commit:** `test(characterization): freeze penalty/objective golden values from de_history`

- [x] 4. Golden references: dtOO export
  - **What:** Add `tests/characterization/test_golden_dtoo_export.py` + `golden/dtoo_export.json`: in the dtOO environment, run the existing `turbine_runner/dtoo_export.py` with the fixed tistos state; freeze: output `runner.msh` checksum (sha256), generated `design.json` content, and the env-override matrix (each of DTOO_CASE_DIR/DTOO_STATE/DTOO_MECH_VOLUME/DTOO_ADJUST_PLUGIN/DTOO_DESIGN_JSON/DTOO_OUTPUT_MSH set vs unset → expected behavior incl. error cases). Mark the whole test module `pytest.mark.skipif` when the dtOO env is not importable.
  - **References:** `turbine_runner/dtoo_export.py`; dtOO submodule (empty locally — use `atismer/dtoo-opensuse:stable` container or cluster `source ~/pe`).
  - **Acceptance:** export reproduces checksum on rerun; override matrix behaves as frozen; skip-path emits a clear message.
  - **QA happy:** `docker run --rm -v "$PWD":/work -w /work atismer/dtoo-opensuse:stable python -m pytest tests/characterization/test_golden_dtoo_export.py -q` → pass → evidence `todo-4-happy.log`.
  - **QA failure:** point DTOO_CASE_DIR at a nonexistent dir → export must raise the frozen error type → evidence `todo-4-failure.log`.
  - **Commit:** `test(characterization): freeze dtOO export golden checksum and env-override matrix`

- [x] 5. Golden references: config dataclass roundtrip
  - **What:** Add `tests/characterization/test_golden_config.py` + `golden/config_roundtrip.json`: for all **11** config dataclasses — `MaterialConfig`, `BCConfig`, `MeshConfig`, `SolverConfig`, `DesignConfig` (:176), `OptimizationConfig` (:212), `DEConfig`, `CFDConfig`, `ObjectiveConfig`, `WetModeConfig`, `OutputConfig` (:370) — build the exact instances the current tistos run uses, `asdict` → JSON → reconstruct → assert equality; freeze the JSONs. (`OptimizationConfig` is load-bearing: carries `Z_guidevanes`, `n_rpm`, `margin_hz`, `penalty_k`; imported by objective.py/optimize.py.)
  - **References:** `turbine_runner/config.py`.
  - **Acceptance:** roundtrip equality holds; frozen JSONs committed.
  - **QA happy:** pytest → pass → evidence `todo-5-happy.log`.
  - **QA failure:** remove one field from a frozen JSON → reconstruction must raise (missing-field error) → evidence `todo-5-failure.log`.
  - **Commit:** `test(characterization): freeze config dataclass roundtrip references`

- [x] 6. pytest-xdist for the test suite
  - **What:** Add `pytest-xdist` to dev dependencies; configure `addopts = "-n auto"` guard (fall back to serial when xdist missing); verify the beam + characterization tests pass under `-n 4`. Tests that use MPI/SLEPc or shared worker dirs get `pytest.mark.serial` (xdist groups them onto one worker); document the marker policy in `tests/README.md`.
  - **References:** `pyproject.toml`, `tests/`, `demo/beam/beam_fem_validation.py`.
  - **Acceptance:** `python -m pytest tests/characterization -n 4 -q` passes; no test depends on execution order (document any that must stay serial with `pytest.mark.serial`).
  - **QA happy:** run with `-n 4` → pass → evidence `todo-6-happy.log` (include walltime vs serial).
  - **QA failure:** temporarily introduce an order-dependent probe test → confirm xdist run exposes it → remove probe → evidence `todo-6-failure.log`.
  - **Commit:** `test(infra): enable pytest-xdist parallel test runs`

### Wave 2 — Package & refactor

- [x] 7. Package skeleton `src/eigenfrequencies/`
  - **What:** Create `src/eigenfrequencies/` with subpackages: `io/`, `solver/`, `bc/`, `materials/`, `penalty/`, `added_mass/`, `validation/`, `adapters/` (with `adapters/dtoo/`), `optimize/`, `mcp/`, plus root modules `config.py`, `provenance.py`, `version.py`. Move the **11** config dataclasses (`MaterialConfig`, `BCConfig`, `MeshConfig`, `SolverConfig`, `DesignConfig`, `OptimizationConfig`, `DEConfig`, `CFDConfig`, `ObjectiveConfig`, `WetModeConfig`, `OutputConfig` — real class names, unchanged) into `src/eigenfrequencies/config.py` with TWO fixes: (a) `turbine_runner/config.py:16-29` reads `templateState.xml` AT IMPORT TIME (`_N_RPM_DEFAULT`, feeding `OptimizationConfig.n_rpm` :230) — REMOVE that import-time filesystem/dtOO read; `n_rpm` becomes a REQUIRED config scalar (the dtOO adapter supplies it from `templateState.xml` at runtime). (b) `CFDConfig.omega` (:292, `2.0*math.pi*_N_RPM_DEFAULT/60.0`) has the SAME class-definition-time dependency — make `omega` derive from `n_rpm` at runtime (`__post_init__` or property); removing `_N_RPM_DEFAULT` must not break the class definitions. DELETE the empty skeleton dirs `src/geometry/`, `src/optimization/`, `src/solver/`, `src/io/` (replaced by the package). Update `pyproject.toml`: `[tool.setuptools.packages.find] where = ["src"]`; keep project name `eigenfrequencies`, v0.1.0, MIT.
  - **References:** `turbine_runner/config.py`, `pyproject.toml`, `src/` skeleton; draft decisions #1/#2.
  - **Acceptance:** `pip install . --no-deps` (in a dolfinx env) succeeds; `python -c "import eigenfrequencies; from eigenfrequencies.config import MaterialConfig, BCConfig, MeshConfig, SolverConfig, DesignConfig, OptimizationConfig, DEConfig, CFDConfig, ObjectiveConfig, WetModeConfig, OutputConfig"` works; `python -c "import eigenfrequencies.config"` succeeds in an env with NO dtOO, NO Pyro5, and cwd containing no `templateState.xml` (no import-time filesystem dependency); `python -c "from eigenfrequencies.config import CFDConfig; assert abs(CFDConfig(n_rpm=90.0).omega - 2*3.141592653589793*90/60) < 1e-12"` (omega derived at runtime); golden config roundtrip test (todo 5) passes importing from BOTH old and new locations during transition.
  - **QA happy:** container: `uv pip install . --no-deps && python -c "import eigenfrequencies"` → evidence `todo-7-happy.log`.
  - **QA failure:** `python -c "import src.solver"` → must fail (skeleton removed) → evidence `todo-7-failure.log`.
  - **Commit:** `refactor(package): create src/eigenfrequencies skeleton, move config dataclasses, drop empty src skeleton`

- [x] 8. Port solver core
   - **What:** Move `turbine_runner/solver.py` → `src/eigenfrequencies/solver/`: `core.py` (generic `ModalSolver` — renamed from `RunnerModalSolver`, BC injected not hardcoded), `scipy_backend.py` (clamped path, sparse free-DOF slice, no densification), `slepc_backend.py` (free-free shift-invert σ=-1, MUMPS; CG+GAMG fallback), `rayleigh.py` (Rayleigh-quotient refinement). Preserve MPI behavior (dolfinx) exactly. No runner-specific names remain in the package.
   - **References:** `turbine_runner/solver.py`; `VALIDATION_summary.md` (P2/SLEPc decisions).
   - **Acceptance:** golden solver tests (todo 2) pass importing ONLY from `eigenfrequencies.solver`; `grep -ri "tistos\|runner" src/eigenfrequencies/solver/` is empty.
   - **QA happy:** container pytest `tests/characterization/test_golden_solver.py` → pass → evidence `todo-8-happy.log`.
   - **QA failure:** solve with an unsupported (element, backend) combination → must raise a typed `SolverConfigError` (new) with a readable message → evidence `todo-8-failure.log`.
   - **Commit:** `refactor(solver): port generic ModalSolver (scipy clamped + SLEPc free-free) into package`

- [x] 9. Port mesh/result IO
   - **What:** Move `turbine_runner/mesh_prep.py` → `src/eigenfrequencies/io/load.py` (mesh load + volume verification) and `src/eigenfrequencies/io/axis.py` (axis discovery, as importable function); move the XDMF/VTK/JSON writers from `turbine_runner/main.py` + `turbine_runner/evaluate.py` → `src/eigenfrequencies/io/results.py` (headless JSON-line mode preserved as `write_result_line`).
   - **References:** `turbine_runner/mesh_prep.py`, `turbine_runner/main.py`, `turbine_runner/evaluate.py`.
   - **Acceptance:** golden solver tests still pass (they exercise load path); `write_result_line` output byte-identical to a frozen sample line (add that sample to `golden/` in this todo).
   - **QA happy:** pytest characterization + a new `tests/io/test_results_writer.py` → pass → evidence `todo-9-happy.log`.
   - **QA failure:** load a mesh file with zero volume cells → typed `MeshVerificationError` → evidence `todo-9-failure.log`.
   - **Commit:** `refactor(io): port mesh loading/axis discovery and result writers into package`

- [x] 10. Port bc/materials/penalty/added_mass
   - **What:** Create `src/eigenfrequencies/bc/` (clamp/free-free/foil-clamp BC builders; hub-clamp logic extracted from current config usage), `materials/` (Material presets incl. Laval bronze: E=75.854 GPa, ρ=8910 kg/m³, ν=0.34), `penalty/` (forbidden-band penalty + kinematic blade-passing band Z·n with harmonics — port from `turbine_runner/optimization.py` and the resonance part of `objective.py`; `cfd_scalar` tanh + `combined_objective` → `src/eigenfrequencies/penalty/objective.py`), `added_mass/` (existing interface + ~15% placeholder shift preserved; `rayleigh_ratios` stays `NotImplementedError`). FIX the known latent bug while porting: `turbine_runner/optimize.py:200-201` sets `opt_cfg.f_min`/`f_max`, but `OptimizationConfig` (`config.py:211-236`) defines `freq_min`/`freq_max` — the ported code must use the real field names (the legacy file itself moves to `legacy/` untouched in todo 12).
   - **References:** `turbine_runner/config.py`, `turbine_runner/optimization.py`, `turbine_runner/objective.py`, `turbine_runner/added_mass.py`, `turbine_runner/optimize.py` (field-name bug); draft decisions (a)/(b) (penalty-not-Pareto, dry-now-wet-later).
   - **Acceptance:** golden objective tests (todo 3) pass importing ONLY from the package; `python -c "from eigenfrequencies.added_mass import rayleigh_ratios"` + call raises `NotImplementedError`; `grep -rn "\bf_min\b\|\bf_max\b" src/eigenfrequencies/` is empty (real fields `freq_min`/`freq_max` used).
   - **QA happy:** pytest `test_golden_objective.py` → pass → evidence `todo-10-happy.log`.
   - **QA failure:** call the wet path → `NotImplementedError` (must NOT silently return a number beyond the documented placeholder) → evidence `todo-10-failure.log`.
   - **Commit:** `refactor(physics): port bc/materials/penalty/added_mass modules into package`

- [x] 11. Port validation suite into package
   - **What:** Move beam validation logic → `src/eigenfrequencies/validation/beam/` (analytical Euler-Bernoulli comparison, cos·cosh=-1 roots) with `tests/validation/test_beam.py`; move the Laval disc validation → `src/eigenfrequencies/validation/testcase/` (opt-in via `RUN_TESTCASE_VALIDATION=1`, unchanged skip semantics, P2/SLEPc settings from VALIDATION_summary.md); keep `demo/beam/` as a thin example using the package (TUI + spline demo keep working, importing from the package).
   - **References:** `demo/beam/beam_fem_validation.py`, `demo/beam/tui.py`, existing repo test using `RUN_TESTCASE_VALIDATION`, `VALIDATION_summary.md`.
   - **Acceptance:** `pytest tests/validation -q` passes (disc test skips without env var + without big RAM, with clear message); `RUN_TESTCASE_VALIDATION=1` path documented; beam TUI starts (smoke: import + `--help` or scripted entry).
   - **QA happy:** `pytest tests/validation -q` → pass/skip-with-message → evidence `todo-11-happy.log`.
   - **QA failure:** corrupt one analytical root constant in a probe copy → beam test must fail with the analytical/FEM delta named → revert → evidence `todo-11-failure.log`.
   - **Commit:** `refactor(validation): port beam + Laval disc validation suites into package`

- [x] 12. Thin out `turbine_runner/`
  - **What:** Delete from `turbine_runner/` all logic now living in the package; `turbine_runner/` keeps only: its run/config driver (importing `eigenfrequencies`), cluster/SLURM scripts, and dtOO project wiring (`dtoo_export.py`, `server_de.py`, `optimize_de.py` stay until todos 19/24-26 replace them — mark each with a `# SUPERSEDED-BY:` comment pointing at the package module once its replacement lands). `optimize.py` (legacy) and `optimize_multi.py`: move under `turbine_runner/legacy/` with a README note (NOT deleted — de_state/de_history compatibility).
  - **References:** `turbine_runner/` (all modules), wave-2 todos above.
  - **Acceptance:** `grep -rn "def combined_objective\|class RunnerModalSolver\|def rayleigh_ratios" turbine_runner/` returns only re-export/import lines; the full characterization + validation suites pass. EXPLICIT keep/move table (verify every row): KEEP as driver = `dtoo_export.py`, `server_de.py`, `optimize_de.py` (until todos 19/24-26 supersede them), `cluster/` SLURM scripts, `legacy/{optimize.py,optimize_multi.py}`, `turbine_runner/README.md` (stays as DRIVER readme — its generic content migrates to `docs/` in todo 41); MOVED to package = solver/mesh_prep/evaluate/main-logic/config/optimization/objective/added_mass/cfd_eval.
  - **QA happy:** full `pytest tests -n 4 -q` → pass → evidence `todo-12-happy.log`.
  - **QA failure:** `python -c "import turbine_runner.solver"` → ImportError (module gone) → evidence `todo-12-failure.log`.
  - **Commit:** `refactor(turbine_runner): reduce to thin dtOO project driver, archive legacy optimizers`

- [x] 13. Golden green against the new package
  - **What:** Switch ALL characterization tests to import only from `eigenfrequencies.*`; run the complete suite (characterization + validation + io) in the container; record a coverage-style delta report (which old-module line now maps to which new-module path) as `.omo/evidence/eigenfrequencies-final-design/todo-13-module-map.md`.
  - **References:** todos 2–12.
  - **Acceptance:** 100% of golden tests pass within tolerances; module-map evidence file exists; no test imports from `turbine_runner` anymore except driver-integration tests explicitly marked as such.
  - **QA happy:** container `pytest tests -n 4 -q` → all green → evidence `todo-13-happy.log`.
  - **QA failure:** pin one golden tolerance to 0.0 (exact) in a probe → document result (pass or fail) to demonstrate the tolerance choice is load-bearing → revert → evidence `todo-13-failure.log`.
  - **Commit:** `test(characterization): green against eigenfrequencies package, add module map`

### Wave 3 — YAML config + CLI

- [x] 14. YAML config module + example configs
   - **What:** Add `src/eigenfrequencies/config_yaml.py`: `load_config(path) -> RunConfig` (YAML → the existing dataclass tree; strict: unknown keys raise `ConfigError` naming the dotted path; missing required fields raise with the field list), `dump_config(config, path)`. `n_rpm` is a REQUIRED field (no env/file-derived default — see todo 7). YAML library: PyYAML. Add `examples/configs/{beam,testcase_laval,tistos}.yaml` reproducing exactly the three golden configurations from wave 1.
   - **References:** `src/eigenfrequencies/config.py`; golden JSONs from todos 2/5; draft decision #4.
   - **Acceptance:** YAML→dataclass→YAML roundtrip is stable (second dump byte-identical); the three example YAMLs reproduce the golden configs exactly (test compares dataclass trees); unknown-key and missing-field errors verified.
   - **QA happy:** `pytest tests/config -q` → pass → evidence `todo-14-happy.log`.
   - **QA failure:** feed YAML with typo key `materail:` → `ConfigError` naming `materail` → evidence `todo-14-failure.log`.
   - **Commit:** `feat(config): YAML config loader/dumper with strict validation + example configs`

- [x] 15. JSON Schema export
   - **What:** Add `src/eigenfrequencies/schema.py`: generate JSON Schema for the full config from the dataclass tree (single source of truth = dataclasses; hand-maintained mapping is NOT allowed — derive programmatically, with a field-parity test). Write the artifact to `schema/eigenfrequencies-config.schema.json` (committed). The schema is DETERMINISTIC: dynamic env-dependent defaults (e.g. the removed import-time `n_rpm` read) are EXCLUDED — required fields stay required in the schema. This schema is what the MCP `get_config_schema` tool will serve (todo 35).
   - **References:** `src/eigenfrequencies/config.py`, `examples/configs/*.yaml`; draft decisions #4/#9.
   - **Acceptance:** the 3 example YAMLs validate against the schema (jsonschema lib); field-parity test fails when a dataclass field is added/removed without regenerating; regeneration is one command (`python -m eigenfrequencies.schema --out schema/`).
   - **QA happy:** `python -m eigenfrequencies.schema --out schema/ && python -c "import jsonschema, yaml, json; jsonschema.validate(yaml.safe_load(open('examples/configs/beam.yaml')), json.load(open('schema/eigenfrequencies-config.schema.json')))"` → no error → evidence `todo-15-happy.log`.
   - **QA failure:** add a probe field to a dataclass → parity test must fail → revert → evidence `todo-15-failure.log`.
   - **Commit:** `feat(config): derived JSON Schema export with field-parity guard`

- [x] 16. CLI: solve + validate
  - **What:** Add `src/eigenfrequencies/cli.py` (typer app, entry point `eigenfrequencies` via `[project.scripts]`): `solve --config PATH [--mesh PATH] [--out DIR] [--json]` (runs modal solve, writes result JSON + optional XDMF/VTK), `validate --suite beam|testcase [--full]` (runs the validation suites; `--full` forces the big-RAM Laval case). Exit codes: 0 ok, 2 config error, 3 solve error, 4 validation deviation.
  - **References:** todos 8–11, 14; `turbine_runner/main.py` + `evaluate.py` (current behavior to replicate).
  - **Acceptance:** `eigenfrequencies solve --config examples/configs/beam.yaml --json` prints freqs matching golden within 1e-4; `validate --suite beam` exits 0; `--help` documents every flag.
  - **QA happy:** container `eigenfrequencies solve --config examples/configs/beam.yaml --out /tmp/run1` + freq check → evidence `todo-16-happy.log` (+ result JSON).
  - **QA failure:** `solve --config /nonexistent.yaml` → exit 2 with message → evidence `todo-16-failure.log`.
  - **Commit:** `feat(cli): typer app with solve and validate subcommands`

- [x] 17. CLI: optimize + report
  - **What:** Extend the CLI: `optimize --config PATH --optimizer de|pso|cmaes|bo|rl [--islands N] [--workers N] [--resume PATH] [--budget N]` (wired to the registry from todo 24; backends not yet implemented must exit 2 with "not installed/not implemented yet" — they land in wave 5/6), `report --run-dir PATH` (summary: best design, objective breakdown, freq table vs forbidden band; if a validation reference exists for the machine, include the comparison table).
  - **References:** todos 14/16; `turbine_runner/optimize_de.py` (current CLI-ish behavior); draft decision #4.
  - **Acceptance:** `optimize --config examples/configs/beam.yaml --optimizer de --budget 50` runs the beam-spline optimization and writes `optimization_result.json`; `report` renders its summary; unknown `--optimizer xyz` → exit 2.
  - **QA happy:** container run of the above + `report --run-dir` → evidence `todo-17-happy.log`.
  - **QA failure:** `--optimizer pso` BEFORE todo 27 exists → exit 2 with clear "not available" message (proves graceful degradation) → evidence `todo-17-failure.log`.
  - **Commit:** `feat(cli): optimize and report subcommands with optimizer registry wiring`

- [x] 18. Run provenance
  - **What:** Add `src/eigenfrequencies/provenance.py`: every solve/validate/optimize run writes `provenance` into its result JSON: `{config_snapshot (asdict), git_commit, git_dirty (bool), package_version, python_version, timestamp_utc, hostname, slurm_job_id (null when absent), container_image (env override PROVENANCE_CONTAINER, null default)}`. Git info via `subprocess git rev-parse HEAD` (no new dep).
  - **References:** draft decision #4 (cluster runs = config file + commit hash); todos 16/17.
  - **Acceptance:** all three subcommands emit complete provenance; `git_dirty=true` when tree has modifications (test: probe-file → dirty flag flips); result JSON schema documented in code docstring.
  - **QA happy:** container solve → inspect result JSON fields → evidence `todo-18-happy.log` (+ JSON).
  - **QA failure:** run inside a copied source tree WITHOUT `.git` → provenance still written with `git_commit=null` + warning, run does NOT crash → evidence `todo-18-failure.log`.
  - **Commit:** `feat(provenance): embed config snapshot + commit hash + environment in every result`

### Wave 4 — dtOO adapter layer

- [x] 19. Adapter core + machine YAML schema
  - **What:** Add `src/eigenfrequencies/adapters/dtoo/`: `machine_yaml.py` (loader + dataclass `MachineAdapterConfig`: `name, case_dir, state, mech_volume, adjust_plugin, design: {label: {min, max}}, mesh_scale_factor (float, default 1.0), bc_template (hub_clamp|foil_clamp|free_free + params), axis (auto|explicit vector)`), `export.py` (generalized export pipeline ported from `turbine_runner/dtoo_export.py`: run dtOO with the machine YAML → produce volume mesh; apply `mesh_scale_factor` on import — this is the explicit fix for the non-physical-units caveat; env overrides preserved), `adapter.py` (high-level: `DtooAdapter(machine_yaml_path).export_mesh(design_values) -> mesh_path`, `.bc()`, `.design_bounds()`).
  - **References:** `turbine_runner/dtoo_export.py`, `turbine_runner/mesh_prep.py` (axis discovery), `src/eigenfrequencies/bc/`; draft decisions #5/#6.
  - **Acceptance:** adapter core importable without dtOO present (dtOO import is lazy inside export); machine YAML strict-validated (unknown key → `ConfigError`); unit tests for loader + scale application (synthetic mesh, scale 0.01 → bbox check).
  - **QA happy:** `pytest tests/adapters -q` → pass → evidence `todo-19-happy.log`.
  - **QA failure:** machine YAML with `design: {x: {min: 1, max: 0}}` (min>max) → `ConfigError` → evidence `todo-19-failure.log`.
  - **Commit:** `feat(adapters): dtOO adapter core with declarative per-machine YAML + mesh scale factor`

- [x] 20. Scale/axis helper CLI utilities
  - **What:** Add CLI group `eigenfrequencies dtoo`: `discover-axis --mesh PATH` (print discovered rotation axis + confidence), `measure-scale --mesh PATH --physical-length M --feature-desc TEXT` (measure bbox/dimension, propose `mesh_scale_factor`, print YAML snippet to paste into the machine file).
  - **References:** `turbine_runner/mesh_prep.py` (axis discovery), todo 19.
  - **Acceptance:** running `measure-scale` on the tistos coarse mesh with its known physical runner diameter prints the factor that brings the bbox to physical size (document the measured value in evidence); `discover-axis` output matches the axis used by the current tistos run.
  - **QA happy:** container run both commands on the tistos coarse mesh → evidence `todo-20-happy.log`.
  - **QA failure:** `measure-scale --physical-length -5` → exit 2 with validation message → evidence `todo-20-failure.log`.
  - **Commit:** `feat(cli): dtoo helper utilities discover-axis and measure-scale`

- [x] 21. tistos adapter YAML + parity validation
  - **What:** Add `adapters/machines/tistos.yaml` reproducing the current `turbine_runner` tistos setup (case dir, state, mech volume, adjust plugin, the current design labels + bounds, measured scale factor from todo 20, hub_clamp BC template). If the tistos golden solver reference was skipped in todo 2 (no dtOO env), generate it NOW from the current code before switching to the adapter. Validate parity: adapter export → same mesh checksum as golden (todo 4); adapter-driven solve → freqs match golden tistos-coarse within 1e-4 / MAC ≥ 0.999.
  - **References:** `turbine_runner/dtoo_export.py` + its current tistos settings; todos 2/4/19/20.
  - **Acceptance:** parity checks pass in the dtOO environment; `tistos.yaml` committed with a header comment citing the source settings.
  - **QA happy:** dtOO container: export + solve + golden comparison → evidence `todo-21-happy.log`.
  - **QA failure:** perturb `mesh_scale_factor` by 1% in a probe YAML → solve must shift freqs and the golden comparison must FAIL (proves scale is load-bearing) → revert → evidence `todo-21-failure.log`.
  - **Commit:** `feat(adapters): tistos machine YAML with export+solve parity validation`

- [x] 22. canadaLight adapter YAML + validation
  - **What:** PRECONDITION first: obtain the dtOO test cases locally — `git submodule update --init dtOO` (submodule is currently EMPTY), or copy from the cluster `~/dtOO/build/test/`, or clone `https://github.com/ihs-ustutt/dtOO.git` inside the dtOO container; record the case source path used in the evidence. If cases are unobtainable: STOP this todo with an explicit blocker note in evidence — do NOT silently skip. PRE-CHECK (record findings in `.omo/evidence/eigenfrequencies-final-design/todo-22-precheck.md`): inspect the dtOO `test/canadaLight` case (machine.xml, machineSave.xml, init.xml, build.py, geo/, Mesh/, xml/) and answer: which state contains a solid/mechanical volume suitable for modal export? which design labels exist? Fallback if no solid state exists: use the lightest buildable geometry state and document the limitation in the pre-check file + machine YAML header. THEN write `adapters/machines/canadaLight.yaml` + validate: export mesh (coarse), free-free solve → sanity checks (6 rigid modes ≈ 0 Hz, first elastic freqs in a plausible range, documented in evidence — no reference data exists, so this is a plausibility validation, not numerical validation).
  - **References:** dtOO repo `test/canadaLight/` (https://github.com/ihs-ustutt/dtOO/tree/main/test); todos 19/20.
  - **Acceptance:** pre-check evidence file exists and answers both questions; adapter YAML committed; plausibility checks pass and are recorded.
  - **QA happy:** dtOO container: pre-check script output + export + solve → evidence `todo-22-happy.log`.
  - **QA failure:** point the YAML at a state that does not exist → adapter must raise `AdapterStateError` naming available states → evidence `todo-22-failure.log`.
  - **Commit:** `feat(adapters): canadaLight machine YAML with pre-check + plausibility validation`

- [x] 23. naca adapter YAML + foil-BC validation
  - **What:** Same dtOO-case precondition as todo 22 (cases must be obtained locally first; blocker note if unobtainable). Add `adapters/machines/naca.yaml` (dtOO `test/naca` case) using the `foil_clamp` BC template (root surface clamp — surface label taken from the YAML, discovered via the helper in todo 20 workflow, documented in evidence). Validate: (a) free-free solve → 6 rigid modes; (b) clamped solve → first bending freq > 0 and P1→P2 convergence direction consistent with the Laval-disc findings (P1 over-stiffens); both coarse.
  - **References:** dtOO repo `test/naca/` (machine.xml, reference meshes); `src/eigenfrequencies/bc/`; `VALIDATION_summary.md` (P1/P2 behavior); todos 19/20/22.
  - **Acceptance:** both solves pass sanity checks (recorded in evidence); BC template demonstrably generic (same builder used for tistos hub-clamp and naca foil-clamp with different params).
  - **QA happy:** dtOO container: export + both solves → evidence `todo-23-happy.log`.
  - **QA failure:** use a foil_clamp YAML whose surface label is absent in the mesh → `BCDefinitionError` listing available labels → evidence `todo-23-failure.log`.
  - **Commit:** `feat(adapters): naca machine YAML validating BC-template genericity (foil clamp)`

### Wave 5 — Optimizer layer + parallelization

- [x] 24. Optimizer protocol + registry + DE backend
  - **What:** Add `src/eigenfrequencies/optimize/protocol.py`: `Optimizer` ABC — `ask(n: int) -> list[Design]`, `tell(designs, objectives)`, `state_dict() -> dict`, `load_state(dict)`, plus `bounds` property; registry (`register(name, factory)`, `create(name, config)`). Port the existing custom DE (`turbine_runner/optimize_de.py`: pop 20, F 0.8, CR 0.9, max_gen 30 defaults; env overrides DE_POP_SIZE etc. preserved) behind the protocol as `de`. Seeded determinism required (seed in config).
  - **References:** `turbine_runner/optimize_de.py`; draft decisions #7/#14.
  - **Acceptance:** seeded DE run on the sphere function reaches < 1e-6 within the default budget; `state_dict`/`load_state` roundtrip reproduces the exact next `ask` batch; existing `de_state*.json` checkpoints load via a small migration shim (documented in code).
  - **QA happy:** `pytest tests/optimize/test_de.py -q` → pass → evidence `todo-24-happy.log`.
  - **QA failure:** `tell` with mismatched lengths (3 designs, 2 objectives) → `ProtocolUsageError` → evidence `todo-24-failure.log`.
  - **Commit:** `feat(optimize): ask/tell Optimizer protocol + registry, port custom DE backend`

- [x] 25. EvaluatorPool abstraction
  - **What:** Add `src/eigenfrequencies/optimize/evaluators/`: `base.py` (`EvaluatorPool` ABC: context manager, `evaluate(list[Design]) -> list[float]`, `shutdown()`; on worker exception: retry once, then raise `EvaluationError` with worker log path), `process_pool.py` (port the ProcessPoolExecutor-spawn + `$TMPDIR/worker_{id}/` isolation from `optimize_de.py`), `pyro_pool.py` (port the Pyro5 RPC evaluator + file-based URI discovery from `turbine_runner/server_de.py`; EVAL_MODE combined/cfd_only/resonance_only preserved). The `Optimizer` backends only ever see the ABC — no backend imports Pyro5.
  - **References:** `turbine_runner/optimize_de.py`, `turbine_runner/server_de.py`; draft decision #14 (Pyro5 = ONE transport, interface not hardcoded).
  - **Acceptance:** DE + ProcessPool reproduces the todo-24 sphere result through the pool; Pyro5 pool passes a loopback integration test (local daemon + URI file) marked `requires_dtoo` + `skipif` when Pyro5 absent (a multi-node variant is marked `requires_slurm`); `grep -rn "Pyro5" src/eigenfrequencies/optimize/ --include="*.py" | grep -v pyro_pool` is empty.
  - **QA happy:** both pools on sphere → evidence `todo-25-happy.log`.
  - **QA failure:** kill one Pyro5 worker mid-batch → pool retries once then raises `EvaluationError` naming the dead worker URI → evidence `todo-25-failure.log`.
  - **Commit:** `feat(optimize): transport-agnostic EvaluatorPool (ProcessPool + Pyro5 backends)`

- [x] 26. Native island model
  - **What:** Add `src/eigenfrequencies/optimize/islands.py`: `IslandOptimizer` wrapping any protocol backend — N subpopulations evolve independently for `migration_interval` generations (default 5), then ring migration: each island sends its best K (default 2) to the next island, replacing worst individuals, with a no-duplicate policy (migrant skipped when already present, per `../de_framework/start_de.py` replacementPolicy concept). Per-island JSON checkpoint (`islands_state/island_{i}.json` after every migration) + `--resume` support. Island count: `--islands N` flag, **default 4** (recommended range 4–8) — islands are population DIVERSITY, not compute parallelism: evaluator parallelism lives in the EvaluatorPool (worker count = `SLURM_NTASKS` on the cluster, cf. `_submit_de_common.sh:31`), NOT in the island count; document this separation in the module docstring and CLI help. Generation semantics: one `ask`+`tell` cycle = one "generation" for migration-interval counting (applies uniformly to DE/PSO/CMA-ES/BO). Caveat to document: CMA-ES islands each learn their own covariance from scratch — valid but often wasteful at small budgets. NO pygmo/pagmo import anywhere.
  - **References:** `../de_framework/start_de.py` (archipelago, save_archi/restart, replacementPolicy — concepts only), `../de_framework/uda_de.py` (DE operators reference); todos 24/25; draft decision #14.
  - **Acceptance:** 4-island run on a multimodal test function (Rastrigin) beats or matches single-island best-objective at equal total budget (recorded in evidence); kill + `--resume` after migration M → run continues from island checkpoints with identical subsequent trajectory (seeded); `grep -rn "pygmo\|pagmo" src/ pyproject.toml environment.yml` is empty.
  - **QA happy:** container 4-island Rastrigin + resume test → evidence `todo-26-happy.log`.
  - **QA failure:** corrupt one island checkpoint JSON → resume raises `CheckpointError` naming the island, other islands unaffected → evidence `todo-26-failure.log`.
  - **Commit:** `feat(optimize): native island model (ring migration, no-duplicate policy, per-island checkpoint/restart)`

- [x] 27. PSO backend (pymoo)
  - **What:** Add `src/eigenfrequencies/optimize/backends/pso.py` wrapping `pymoo.algorithms.so_pso.PSO` behind the protocol (pymoo's ask/tell interface; bounds from config; seeded). Dependency: `pymoo` in the `optimize` extra (todo 39).
  - **References:** todo 24; draft decision #7.
  - **Acceptance:** passes the shared conformance suite (todo 30); sphere convergence recorded.
  - **QA happy:** `pytest tests/optimize -k pso -q` → pass → evidence `todo-27-happy.log`.
  - **QA failure:** import backend with pymoo uninstalled → registry reports "unavailable: pymoo not installed" (no ImportError crash) → evidence `todo-27-failure.log`.
  - **Commit:** `feat(optimize): PSO backend via pymoo`

- [x] 28. CMA-ES backend (cma)
  - **What:** Add `src/eigenfrequencies/optimize/backends/cmaes.py` wrapping `cma.CMAEvolutionStrategy` (native ask/tell; `sigma0` default = 0.3 × bounds range, configurable; seeded).
  - **References:** todo 24; draft decision #7.
  - **Acceptance:** passes conformance suite; sphere convergence recorded.
  - **QA happy:** `pytest tests/optimize -k cmaes -q` → pass → evidence `todo-28-happy.log`.
  - **QA failure:** same unavailable-dep degradation check as todo 27 → evidence `todo-28-failure.log`.
  - **Commit:** `feat(optimize): CMA-ES backend via cma (PyPI name; project colloquially pycma)`

- [x] 29. Bayesian/TPE backend (optuna)
  - **What:** Add `src/eigenfrequencies/optimize/backends/bo.py` wrapping optuna `TPESampler` via optuna's ask/tell API (trials map to designs; seeded; intended for expensive CFD-in-loop evaluations — document the recommendation in the module docstring and `report` output when `--optimizer bo` is used).
  - **References:** todo 24; draft decision #7.
  - **Acceptance:** passes conformance suite; on a 2-D quadratic with budget 30 it beats DE's best-objective at the same budget (recorded — sanity for the sample-efficiency claim, not a hard gate: allow one seeded retry, record both).
  - **QA happy:** `pytest tests/optimize -k bo -q` → pass → evidence `todo-29-happy.log`.
  - **QA failure:** same unavailable-dep degradation check → evidence `todo-29-failure.log`.
  - **Commit:** `feat(optimize): Bayesian/TPE backend via optuna for expensive evaluations`

- [x] 30. Optimizer conformance suite + beam-spline integration
  - **What:** Add `tests/optimize/test_conformance.py` parametrized over `[de, pso, cmaes, bo]`: protocol surface (ask/tell/state roundtrip), seeded determinism (two runs → identical trajectories), bounds respect (no design outside bounds across 200 asks), unavailable-dep degradation. Integration: run the beam-spline optimization demo through the CLI with each backend (budget-capped, coarse) — each must reduce the forbidden-band penalty below the start value (record the penalty trajectories in evidence).
  - **References:** todos 24–29, 17; `demo/beam/` (spline optimization demo).
  - **Acceptance:** all backends pass conformance; 4/4 integration runs improve the objective; evidence includes the trajectory table.
  - **QA happy:** container `pytest tests/optimize -n 4 -q` + 4 CLI runs → evidence `todo-30-happy.log`.
  - **QA failure:** register a deliberately broken probe backend (tell() no-op) → conformance must FAIL naming the violated contract → remove probe → evidence `todo-30-failure.log`.
  - **Commit:** `test(optimize): backend conformance suite + beam-spline integration across backends`

### Wave 6 — RL backend

- [x] 31. gymnasium environment
  - **What:** Add `src/eigenfrequencies/optimize/rl/env.py`: `EigenfreqEnv(gymnasium.Env)` — action space `Box(-1, 1, shape=(dim,))` mapped linearly to the design bounds (from the machine YAML adapter or the plain config bounds); observation = current normalized design vector + last objective value (`Box`); reward = `-objective(design)`; episode terminates at `max_evals` (config, default 200) or when a target objective is reached (optional config); `reset(seed=...)` deterministic. The objective called is the SAME objective interface the other optimizers use (todo 24 path) — no second objective implementation.
  - **References:** `../rl_framework/env_tistos.py` (concept reference: normalized Box, bounds mapping — hydraulic objectives there, ours is modal), todos 14/24; draft decision #8.
  - **Acceptance:** `gymnasium.utils.env_checker.check_env(env)` passes on the beam config; 50 random steps never leave bounds (mapped); reward equals `-combined_objective` from the golden path on a recorded input.
  - **QA happy:** container `pytest tests/rl -q` → pass → evidence `todo-31-happy.log`.
  - **QA failure:** construct env with bounds min>max (bad config) → `ConfigError` at construction (not at first step) → evidence `todo-31-failure.log`.
  - **Commit:** `feat(rl): gymnasium environment over the standard objective interface`

- [x] 32. SB3 integration smoke
  - **What:** Add `examples/rl/train_rl.py`: trains PPO (default; SAC/TD3 selectable via `--algo`) on the beam-spline problem for a tiny budget (`--steps`, default 2048) and writes `rl_history.json` (reward per eval). Add `tests/rl/test_sb3_smoke.py`: 2-update PPO + SAC + TD3 construction and one `learn()` call each on the beam env (tiny budget, `skipif` when SB3 absent). Deps: `stable-baselines3`, `gymnasium` in the `rl` extra (todo 39).
  - **References:** todo 31; draft decision #8 (SB3-compatible → PPO/SAC/TD3 out of the box; PBO pluggable later, NOT adopted).
  - **Acceptance:** smoke tests pass; example run writes reward history; `--algo ppo|sac|td3` all construct.
  - **QA happy:** container `python examples/rl/train_rl.py --algo ppo --steps 512` → completes, JSON written → evidence `todo-32-happy.log`.
  - **QA failure:** `--algo dqn` → exit 2 "unsupported for continuous Box action space" → evidence `todo-32-failure.log`.
  - **Commit:** `feat(rl): SB3 training example + PPO/SAC/TD3 smoke tests`

- [x] 33. Offline-RL exporter (de_history → d3rlpy)
  - **What:** Add `src/eigenfrequencies/optimize/rl/offline_export.py`: parse `turbine_runner/de_history*.jsonl` (and any future history JSONL via `--history PATH`) → d3rlpy `MDPDataset` (observation = normalized design, action = next design in the recorded trajectory, reward = `-(f_{t+1} - f_t)` improvement shaping with a `--reward raw|improvement` flag, terminals at episode/generation boundaries as recorded; normalization bounds come from the machine YAML (todo 19) or the plain config (todo 7) — never from the history files alone. Smoke: `tests/rl/test_offline.py` exports the real history files and runs 2 CQL epochs on the dataset (`skipif` d3rlpy absent). CLI: `eigenfrequencies rl-export --history ... --out dataset.d3`.
  - **References:** `turbine_runner/de_history*.jsonl`; `../rl_framework/pbo.py` (offline-RL context only); draft decision #8.
  - **Acceptance:** dataset row count == parseable history rows (malformed rows counted + reported, not fatal); CQL smoke completes and writes metrics JSON.
  - **QA happy:** container `eigenfrequencies rl-export --history turbine_runner/ --out /tmp/ds.d3 && pytest tests/rl/test_offline.py -q` → evidence `todo-33-happy.log`.
  - **QA failure:** history file with one corrupt JSON line → exporter reports `skipped=1`, still exports the rest → evidence `todo-33-failure.log`.
  - **Commit:** `feat(rl): offline-RL exporter from DE history to d3rlpy datasets`

### Wave 7 — MCP server

- [x] 34. Job manager
  - **What:** Add `src/eigenfrequencies/mcp/jobs.py`: `JobStore` rooted at `.eigenfrequencies/jobs/<job_id>/` (`status.json` {state: queued|running|done|failed, exit_code, started/finished, provenance}, `result.json`, `stderr.log`, `stdout.log`); `submit(kind, config)` spawns the matching CLI command as a subprocess (or, with `--cluster`, submits the existing SLURM script via `sbatch` and polls `sacct`); `status(job_id)`; `fetch(job_id)`. Never blocks the caller: submit returns immediately with the job id.
  - **References:** todos 16–18; cluster SLURM scripts in `turbine_runner/` (or `cluster/`); draft decision #9.
  - **Acceptance:** local beam job: submit → poll until done → fetch → freqs match golden; failed job (bad config) → state `failed`, stderr captured; cluster path unit-mocked (sbatch/sacct calls recorded) + documented for real-cluster use.
  - **QA happy:** container `pytest tests/mcp/test_jobs.py -q` → pass → evidence `todo-34-happy.log`.
  - **QA failure:** fetch unknown job id → `JobNotFoundError`; status of a killed process → `failed` with exit code → evidence `todo-34-failure.log`.
  - **Commit:** `feat(mcp): async job store/manager (submit/poll/fetch, SLURM path preserved)`

- [x] 35. fastmcp tools
  - **What:** Add `src/eigenfrequencies/mcp/server.py` (fastmcp, stdio transport; entry point `eigenfrequencies-mcp` via `[project.scripts]`). Tools: `get_config_schema()` → the committed JSON Schema artifact; `solve_modal(config: dict) -> {job_id}` (validates config against schema first — invalid config returns a structured error, no job); `validate(suite: str) -> {job_id}`; `optimize_start(config, optimizer, islands?, workers?, budget?) -> {job_id}`; `job_status(job_id)`; `fetch_results(job_id) -> result JSON`. All long-running tools are async-submit ONLY (never blocking) per decision #9.
  - **References:** todos 15/34; draft decision #9.
  - **Acceptance:** each tool callable via fastmcp test client; schema tool returns bytes identical to `schema/eigenfrequencies-config.schema.json`; invalid config rejected before job creation.
  - **QA happy:** container `pytest tests/mcp/test_tools.py -q` → pass → evidence `todo-35-happy.log`.
  - **QA failure:** `solve_modal({"materail": ...})` → structured validation error naming the field, zero jobs created → evidence `todo-35-failure.log`.
  - **Commit:** `feat(mcp): fastmcp stdio server with schema/solve/validate/optimize/job tools`

- [x] 36. MCP resources + guardrails
  - **What:** Add resources to the server: `results://{job_id}` (job result JSONs), `machines://` (the adapter machine YAML catalog: tistos, canadaLight, naca), `docs://validation` (VALIDATION_summary.md + beam validation summary), `docs://howto/{install,adapters,cluster,mcp}` (from todo 41; stub pages acceptable until then — but links must resolve). Guardrails enforced in code review + a test: the server exposes NO tool that reads source code structure or answers code-knowledge questions (that is graphify's layer); resources are read-only; the job dir is the ONLY writable path.
  - **References:** todo 35; draft decisions #9/#11.
  - **Acceptance:** resources listable + readable via test client; `grep` of `mcp/` shows no code-graph/query tooling; a test asserts the tool registry contains exactly the 6 tools from todo 35 (no more).
  - **QA happy:** container `pytest tests/mcp/test_resources.py -q` → pass → evidence `todo-36-happy.log`.
  - **QA failure:** probe tool `explain_codebase` added temporarily → registry-shape test must FAIL → remove probe → evidence `todo-36-failure.log`.
  - **Commit:** `feat(mcp): result/machine/docs resources with explicit capability guardrails`

- [x] 37. MCP client config + end-to-end smoke
  - **What:** Add client setup snippets to docs (opencode `mcp` config block + Claude-Desktop-style JSON for `eigenfrequencies-mcp` stdio) and an end-to-end test driving the server through a real stdio session (fastmcp Client): get schema → build minimal beam config programmatically → submit solve → poll → fetch → compare freqs to golden (1e-4).
  - **References:** todos 34–36, 15; user's opencode setup precedent (graphify MCP servers).
  - **Acceptance:** e2e test passes; docs snippet copy-pasteable (paths repo-relative with env var override); LLM-usable error messages (structured, field-named) verified on one invalid call.
  - **QA happy:** container `pytest tests/mcp/test_e2e.py -q` → pass → evidence `todo-37-happy.log`.
  - **QA failure:** kill the server process mid-poll → client sees a transport error, job state on disk still consistent (recoverable) → evidence `todo-37-failure.log`.
  - **Commit:** `test(mcp): stdio end-to-end smoke + client configuration snippets`

### Wave 8 — Knowledge, distribution, docs

- [x] 38. graphify update + corpus ingest
  - **What:** Run `graphify update .` (AST-only) after the refactor settles; ingest the docs/validation corpus (documentation.md, VALIDATION_summary.md, examples/configs, adapters/machines/*.yaml headers) into the graph per the project's graphify workflow; verify orientation queries return the NEW module paths.
  - **References:** `AGENTS.md` (graphify rules), `graphify-out/`; draft decision #11.
  - **Acceptance:** `graphify query "penalty forbidden band"` returns `src/eigenfrequencies/penalty/` nodes (not stale `turbine_runner/optimization.py` as primary); `graphify path "ModalSolver" "DtooAdapter"` resolves; stats (node/edge counts) recorded in evidence.
  - **QA happy:** run update + the two queries above → evidence `todo-38-happy.log`.
  - **QA failure:** `graphify query "RunnerModalSolver"` must not return live code nodes (only history) — if it does, the update was incomplete; rerun and record → evidence `todo-38-failure.log`.
  - **Commit:** `chore(graph): refresh knowledge graph after package refactor + ingest docs corpus`

- [x] 39. environment.yml + pyproject extras
  - **What:** Add `environment.yml` (conda-forge): `python>=3.11,<3.14`, `fenics-dolfinx=0.11.*`, `slepc4py` PINNED to the validated container version recorded in `VALIDATION_summary.md` (parity with the SLEPc setup that produced the ≤3% validation), `petsc4py`, `mpi4py`, `pyyaml`, `typer`, `jsonschema`. Add pyproject `[project.optional-dependencies]`: `optimize = [pymoo, cma, optuna]`, `rl = [gymnasium, stable-baselines3, d3rlpy]`, `mcp = [fastmcp]`, `dev = [pytest, pytest-xdist, jsonschema, ruff]`, `dtoo = [Pyro5]`; document install: `conda env create -f environment.yml`, `conda activate eigenfrequencies`, `uv pip install . --no-deps`, then optional `uv pip install .[optimize,rl,mcp,dev] --no-deps`. NOTE: waves 1–7 QA run in the existing `eigenfrequencies-fenicsx:latest` docker image; this todo validates the conda path for distribution. Also update `pyproject.toml` `requires-python` (currently `>=3.10`, line 6) to `>=3.11,<3.14` for parity with environment.yml.
  - **References:** `pyproject.toml`; draft decisions #3/#7/#8/#9 (dependency surface); cluster apptainer def `cluster/apptainer_fenicsx.def` (`From: dolfinx/dolfinx:stable` — unpinned upstream; validation ran on dolfinx 0.11.x per VALIDATION_summary.md, hence the `0.11.*` pin).
  - **Acceptance:** fresh `conda env create -f environment.yml` succeeds; `python -c "import dolfinx; assert dolfinx.__version__.startswith('0.11')"`; each extra installs and its import smoke passes; `pip install eigenfrequencies` from PyPI is NOT provided and README says why (dolfinx not on PyPI).
  - **QA happy:** fresh env + full `pytest tests -n 4 -q` (skips allowed for missing optional extras only) → evidence `todo-39-happy.log`.
  - **QA failure:** `uv pip install .[optimize] --no-deps` in an env WITHOUT conda dolfinx → import of `eigenfrequencies.solver` fails with the documented "install the conda env first" hint (add the hint to the ImportError message via a guarded import) → evidence `todo-39-failure.log`.
  - **Commit:** `build(dist): conda environment.yml + optional-dependency extras with guarded dolfinx import`

- [x] 40. Dockerfile refresh
  - **What:** Update `docker/fenicsx.Dockerfile`: REMOVE the `pygmo` pip install (current line 3 — decision 14 bans pygmo/pagmo), install `uv`, copy repo, `uv pip install . --no-deps` + `.[optimize,mcp,dev] --no-deps` (rl optional — document why: image size), rebuild `eigenfrequencies-fenicsx:latest`. ALSO remove `pygmo` from `cluster/apptainer_fenicsx.def:18` (`pip install gmsh pygmo matplotlib pyvista scipy plotly` — the Apptainer def mirrors the Dockerfile and must stay in lockstep). Update `.github/workflows/ci.yml` (currently builds this Dockerfile) to the refreshed image/steps.
  - **References:** `docker/fenicsx.Dockerfile`, todo 39.
  - **Acceptance:** `docker run --rm eigenfrequencies-fenicsx:latest eigenfrequencies --help` works; beam validation passes in-container.
  - **QA happy:** rebuild + run `pytest tests/validation/test_beam.py -q` in-container → evidence `todo-40-happy.log`.
  - **QA failure:** `docker run --rm eigenfrequencies-fenicsx:latest python -c "import d3rlpy"` → ImportError expected and documented (rl extra excluded) → evidence `todo-40-failure.log`.
  - **Commit:** `build(docker): refresh fenicsx image with packaged install via uv`

- [x] 41. Documentation set
  - **What:** Write `docs/`: `install.md` (conda+uv primary path; docker path; cluster enroot note), `quickstart.md` (solve the beam YAML in 5 commands), `adapters.md` (authoring a machine YAML: every field, scale-factor workflow with `measure-scale`, BC templates hub_clamp/foil_clamp/free_free, the three shipped machines with their caveats — tistos units, canadaLight pre-check outcome, naca foil clamp), `mcp.md` (server start, client config snippets, the 6 tools + resources, guardrails), `cluster.md` (bwUniCluster 3.0: enroot `pyxis_fenicsx`, `source ~/pe` for dtOO, sbatch scripts, islands = SLURM_NTASKS, provenance = config + commit hash). Update `documentation.md` roadmap section: wet/FSI + NSGA-II remain future work, now pointing at the new module paths. Fix stale pre-existing docs: `docs/source/api/solver.md` references `eigenfrequencies.solver.ModalSolver` (did not exist before this refactor — align with the real ported names) and the `docs/source` quickstart's old docker-script references → point at the new package/CLI.
  - **References:** todos 14–23, 34–37, 39; `documentation.md` §6.
  - **Acceptance:** every command in quickstart.md + cluster.md is executed during F3 and works as written; adapters.md covers every MachineAdapterConfig field (cross-check test or manual checklist in evidence).
  - **QA happy:** follow quickstart.md verbatim in a fresh container → beam result → evidence `todo-41-happy.log`.
  - **QA failure:** docs link check (markdown links to files/paths) → no dead links → evidence `todo-41-failure.log` (record the tool run).
  - **Commit:** `docs: install/quickstart/adapters/mcp/cluster documentation set`

- [x] 42. Public-repo preparation
  - **What:** Ensure `LICENSE` (MIT, matching pyproject) exists with IHS University of Stuttgart copyright; rewrite `README.md` (what it is, validation highlights: beam analytical + Laval disc ≤3% vs experiment/ANSYS, install, quickstart, adapter list, MCP one-liner, roadmap note wet/FSI); audit `.gitignore` (add: `.eigenfrequencies/jobs/`, `islands_state/`, `*.d3`, `__pycache____` if missing; KEEP `de_state*.json`/`de_history*.jsonl` ignored or document them as run artifacts — do NOT delete the existing tracked ones, no history rewrite); secrets sweep: grep for tokens/passwords/private keys across the tree (Pyro URI hostnames are acceptable and documented). UNTRACK `graphify-out/`: it is listed in `.gitignore` (line ~57) but files are still TRACKED in the index (git status shows deletions) — run `git rm -r --cached graphify-out/` so the directory stays ignored locally but leaves the repo index; NO history rewrite.
  - **References:** `pyproject.toml` (MIT declared), `README.md`, `.gitignore`; draft decision #3.
  - **Acceptance:** LICENSE/README/gitignore in place; sweep report committed to evidence with zero secrets found (or each finding fixed before commit).
  - **QA happy:** run sweep + render README (markdown lint pass optional) → evidence `todo-42-happy.log`.
  - **QA failure:** plant a probe fake token in a temp file → sweep must flag it → remove → evidence `todo-42-failure.log`.
  - **Commit:** `chore(repo): public-release prep (LICENSE, README, gitignore audit, secrets sweep)`

## Final verification wave

Runs in parallel after ALL todos; ALL must APPROVE; results surfaced to the user before completion is declared.

- [x] F1. Plan compliance audit
  - **What:** For every todo 1–42: verify its acceptance criteria against the repo state and confirm its evidence files exist under `.omo/evidence/eigenfrequencies-final-design/` and contain the recorded commands + outputs. Produce a compliance table (todo → status → evidence path) as `.omo/evidence/eigenfrequencies-final-design/F1-compliance.md`.
  - **Acceptance:** 42/42 rows APPROVE or carry an explicit, user-visible deviation note.

- [x] F2. Code quality review
  - **What:** `ruff check src/ tests/` and `ruff format --check src/` pass (ruff config added to pyproject in this task if absent); no module exceeds ~250 pure LOC without a documented reason in the module docstring; zero dead re-exports from the turbine_runner move; `grep -rn "TODO\|FIXME\|XXX" src/` findings each have an issue reference or are resolved.
  - **Acceptance:** all checks pass; report at `.omo/evidence/eigenfrequencies-final-design/F2-quality.md`.

- [x] F3. Real end-to-end QA matrix
  - **What:** Execute and record: (1) beam validation vs Euler-Bernoulli; (2) Laval disc `RUN_TESTCASE_VALIDATION=1` (cluster/big-RAM if local RAM < 32 GB — record where it ran); (3) tistos adapter export+solve parity; (4) canadaLight + naca adapter solves; (5) CLI e2e: all four subcommands; (6) MCP stdio e2e (schema→solve→fetch); (7) island model: 4-island local run + SLURM smoke on the cluster (islands = 4 explicit, evaluator tasks = SLURM_NTASKS ≈ 20, walltime ≤ 8h) if cluster access is available, else a documented local multi-island run; (8) RL: env checker + PPO smoke + offline export on the real `de_history*.jsonl`; (9) quickstart.md followed verbatim in a fresh container.
  - **Acceptance:** 9/9 items pass with evidence; any cluster-blocked item carries an explicit blocker note for the user instead of a silent skip.

- [x] F4. Scope fidelity audit
  - **What:** Verify the Must-NOT-have list: `grep -rn "pygmo\|pagmo\|hipporag\|figma" src/ pyproject.toml environment.yml docs/ README.md docker/ .github/ cluster/` empty; no PyPI publish workflow (`.github/workflows/` contains none); `added_mass.rayleigh_ratios` still raises NotImplementedError (no wet-mode implementation); no NSGA-II/Pareto axis in optimize/; `git log main..HEAD --oneline` shows all work on `refactor/standalone-tool` and `git diff main --stat` touches no unrelated paths; MCP registry still exactly 6 tools.
  - **Acceptance:** all audits pass; report at `.omo/evidence/eigenfrequencies-final-design/F4-scope.md`.

## Commit strategy

- One conventional commit per todo (message given in the todo); a todo may split into multiple commits when its QA finds and fixes issues — the final commit of the todo must still carry the todo's message (amended or follow-up `fix:` commits are fine).
- All commits on `refactor/standalone-tool` ONLY; never on `cfd-eigenfreq-multiobjective`. No push and no PR without the user's explicit request; merge-back policy is a later user decision.
- Commit messages describe the change only — no attribution trailers, no co-author footers, no generation notes.
- Golden-reference data, schema artifact, and evidence-log pointers belong in the commits that produce them (tests/characterization/golden/, schema/, docs); large run artifacts (meshes, XDMF, .d3 datasets, job dirs) are NEVER committed (covered by .gitignore in todo 42).

## Success criteria

1. `eigenfrequencies` installs via the documented conda+uv flow and `eigenfrequencies solve --config examples/configs/beam.yaml` reproduces the golden eigenfrequencies (rel. ≤ 1e-4) on a fresh machine.
2. Both validation suites pass against the package: beam (always) and Laval disc (`RUN_TESTCASE_VALIDATION=1`, ≤3% vs experiment as in VALIDATION_summary.md).
3. Three machine adapters ship and run: tistos (parity with the pre-refactor setup), canadaLight, naca — new dtOO geometry = new YAML, zero code.
4. `optimize` runs with 5 registered backends (de/pso/cmaes/bo/rl-capable env), island model parallelizes across local workers and evaluator parallelism maps onto SLURM_NTASKS on the cluster, with checkpoint/resume.
5. An LLM client can, through the MCP server alone: fetch the config schema, submit a solve, poll, and fetch validated results — without touching the repo.
6. `graphify` queries resolve to the new package layout; docs (install/quickstart/adapters/mcp/cluster) are verified by literal execution.
7. Every Must-NOT-have holds (F4 audit); every todo's evidence exists (F1 audit); characterization suite proves zero numerical drift from the validated state.
