# eigenfrequencies-final-design — DRAFT (interviewing)

## Meta

- intent: clear (explicit interview override — user invoked /grill-me; adopt-default filter OFF)
- review_required: true  (user said "deep review" 2026-07-28 — dual review momus + oracle REQUIRED before handoff, runs same turn)
- target file: `.omo/plans/eigenfrequencies-final-design.md`
- status: awaiting-approval
- slug note: distinct from existing `eigenfreq_abschluss_deck_prompt.md` (Laval final deck, separate initiative)

## Request summary (user, 2026-07-28)

Finalize the eigenfrequencies framework:
1. eigenfrequencies should become a **standalone tool**
2. **dtOO coupling** so optimization works with ALL geometries available in dtOO (not just tistos runner)
3. **Optimizer layer** — possibly beyond DE (swarm/PSO, ants/ACO, ...?)
4. Question: **MCP server** so an LLM can drive the modal analysis?
5. Question: **code/data graphs** (graphify, HippoRAG) for LLM integration — does it make sense, how?
6. Question: **"Figma Codex"** — user believes it is a code-structuring layer between LLM and code (needs clarification)
7. `/grill-me` — interview user about final design + LLM integration

## Exploration findings (verified in repo)

- Working code lives in `turbine_runner/` (not packaged): config dataclasses, dtoo_export, mesh_prep, solver (`RunnerModalSolver`, scipy clamped / SLEPc free-free, Rayleigh-quotient refinement), evaluate, main, optimization (penalty), objective (cfd+resonance), cfd_eval, added_mass (stub), optimize_de (custom DE, ProcessPoolExecutor spawn, 20 workers), server_de.py (Pyro5 RPC workers, file-based URI discovery), optimize_multi.
- `src/{geometry,io,optimization,solver}/` = **empty skeleton** (only `__init__.py`); pyproject.toml declares packages from src → packaging planned but unexecuted.
- Validation assets: `demo/beam/` (Euler-Bernoulli cantilever comparison, TUI, spline optimization demo); `TestCaseGeomertyMesh.stl` bronze disc free-free vs experiment+ANSYS — **PASSED** (≤3% vs experiment, P2/tet10/SLEPc, VALIDATION_summary.md 2026-07-20).
- Dry mode only: `added_mass.rayleigh_ratios` = NotImplementedError, placeholder ~15% shift. Wet/FSI explicitly roadmap (documentation.md §6).
- dtOO = git submodule (ihs-ustutt/dtOO), **not initialized locally** (empty dir). Coupling via dtoo_export.py: case dir, state, mech volume, adjust plugin, design.json {label: value}.
- Known open caveats: mesh units/scale (~2.5 bbox, non-physical), hub-clamp physicality, CFD column indices, kinematic band partially implemented (deck mentions blade-passing band Z·n implemented, penalty 36.7→14.25).
- No MCP anywhere in repo (grep: zero hits).
- graphify graphs present: eigenfrequencies (647 nodes), domain-2d (separate meshing project, NOT dtoo).
- Cluster: bwUniCluster 3.0, SLURM, enroot pyxis_fenicsx, dtOO native; de_state/de_history checkpointing exists.
- Context: Stuttgart↔Laval exchange (May–Jul 2026) concluded; Abschluss-Deck planned separately.

## Design tree (branches to grill, dependency order)

A. Scope & Definition of Done of "standalone tool" (root)
B. Package architecture (src/ layout, CLI, dtOO as adapter/plugin, distribution)
C. Generic dtOO geometry integration (adapter config, param discovery, BC/units automation)
D. Optimizer layer (interface, which algorithms, library vs custom, HPC path)
E. MCP server (tool surface, transport, deployment, guardrails)
F. Graph/RAG for LLM (graphify extension vs HippoRAG; what knowledge)
G. "Figma Codex" clarification (terminology — fold into E/F discussion)

## Decisions log

| # | Fork | Decision | Status |
|---|------|----------|--------|
| 1 | Scope boundary | **Kern + optionale Layer**: core = generic modal analysis (mesh IO, solver, BCs, added-mass interface, penalty API, validation suite) as pip package + CLI; dtOO adapter + optimizer layer = optional integration modules in same repo (extras); CFD coupling + cluster deployment stay project code; wet/FSI = roadmap | DECIDED 2026-07-28 |
| 2 | Package architecture | **Ein Paket, turbine_runner wird dünn**: `src/eigenfrequencies/` single import package — io/, solver/ (generic: clamped + free-free, scipy + SLEPc), bc/, materials/, penalty/, added_mass/, validation/ (beam + bronze disc shipped as test suite), adapters/dtoo/ (extra), optimize/ (extra). turbine_runner/ shrinks to thin dtOO project driver (config + cluster scripts) importing the package. Library-first (MCP/CLI wrap same API later). | DECIDED 2026-07-28 |
| 3 | Distribution | **Public + conda/docker**: public GitHub repo; `environment.yml` (conda-forge: fenics-dolfinx + slepc4py) + existing Dockerfile + install docs (`conda env create`, then `uv pip install . --no-deps`); NO PyPI release now (dolfinx absent from PyPI → plain-pip installs would break); uv used as fast in-env installer. Open-source framing consistent with Laval final deck. | DECIDED 2026-07-28 |
| 4 | Tool interface | **YAML-Config + volle CLI**: YAML config files (material, bc, mesh, solver, penalty bands); typer CLI subcommands solve/validate/optimize/report; dataclasses stay as internal validation schema; JSON Schema of config exported (needed later by MCP so LLM can generate valid configs); cluster runs = config file + commit hash. | DECIDED 2026-07-28 |
| 5 | dtOO adapter mechanism | **Deklarative YAML pro Maschine**: per-machine adapter config (case dir, state, mech volume, adjust plugin, design labels + bounds, mesh scale factor — solves the non-physical-units caveat explicitly, BC template). New geometry = new YAML, zero code. Axis-discovery + scale measurement remain helper tools. User: note introspection (option 2) on a later TODO list. | DECIDED 2026-07-28 |
| 6 | Target geometries shipped+validated | **tistos + canadaLight + naca** (3 adapter YAMLs). canadaLight = full dtOO case (likely Laval machine; pre-check: solid/mech-volume state present?). naca = full case w/ reference meshes (foil BC tests BC-genericity). simpleAxialRunner + partRotatingMap2dTo3d = later. 16 other dtOO test entries are API/mesh unit tests, not modal-relevant. | DECIDED 2026-07-28 |
| 7 | Optimizer layer | **Interface + DE/PSO/CMA-ES/BO + RL**: small Optimizer protocol (ask/tell) in optimize/ extra. Backends: DE (existing custom, cluster-parallel + Pyro5 path preserved), PSO (pymoo), CMA-ES (pycma), Bayesian/TPE (optuna) for expensive CFD-in-loop runs. NSGA-II = roadmap (penalty decision (a) holds). ACO explicitly rejected (combinatorial, wrong problem class). **PLUS RL backend** (user addition): colleague's start exists at ../rl_framework (gymnasium env_tistos, SB3 custom PBO arXiv:2104.06175, LSTM surrogate, Pyro5 CFD) — not to be adhered to. | DECIDED 2026-07-28 |
| 8 | RL backend shape | **Gymnasium-Env + SB3 + Offline-RL**: generic gymnasium.Env over standard objective interface (design vector → -objective reward; dim from machine YAML). SB3-compatible → PPO/SAC/TD3 out-of-the-box; colleague's PBO stays pluggable later, not adopted. Offline-RL exporter: de_history*.jsonl → d3rlpy dataset (CQL/IQL), train without new FEM evals. Scope: dry-modal objective first (minutes/eval feasible); CFD-in-RL-loop via surrogate/offline only = roadmap. | DECIDED 2026-07-28 |
| 9 | MCP server | **Job-basierter MCP-Server Teil des Plans**: extra `mcp`, fastmcp (stdio), thin layer over same library API as CLI (no second API). Tools: get_config_schema, solve_modal/validate/optimize_start (async submit), job_status, fetch_results; Resources: result JSONs + machine YAML catalog. Never blocking (submit/poll/fetch); cluster runs via existing SLURM path. Precedent: graphify MCP servers already running in user setup. | DECIDED 2026-07-28 |
| 10 | Config editor UI | **Kein UI jetzt**: YAML per Hand + LLM über MCP (schema-validated) as the editor. User pushed 3x on Figma-based config toggles (variables/modes → Figma-MCP → LLM → YAML); websearch verdict delivered (official Figma docs): Code Connect = design-component↔code-component bridge for UI frameworks only (React/SwiftUI/...), no config runtime, cloud+paid seat, not git-versionable → categorically wrong for reproducible cluster runs (Q4 principle config+commit-hash). User then chose no-UI. Schema-generated form (rjsf) parked in Later TODO. | DECIDED 2026-07-28 |
| 11 | Graph/RAG scope | **graphify + MCP-Kontext**: plan includes mandatory `graphify update` after refactor + ingest of docs/validation corpus into graph + curated domain resources in eigenfrequencies-MCP (validation reports, machine catalog, how-tos). Layer clarification delivered: MCP = protocol/capabilities (runtime), graphify = structural code knowledge (dev-side), already served via MCP in user setup — complementary, not contradictory. eigenfrequencies-MCP must NOT serve code-knowledge (no explain_codebase tool — that is graphify's job). HippoRAG explicitly out (roadmap note). | DECIDED 2026-07-28 |
| 12 | Third validation showcase | CORRECTED by user: "diese analyse" = **the FEniCSx modal analysis of this repo on the application case TestCaseGeomertyMesh** — the Laval University data (ANSYS simulation + experimental measurements) received for validation. So the original list collapses to ONE validation story: Laval disc reference data + this repo's FEniCSx analysis of it (VALIDATION_summary.md, PASSED ≤3%). Validation suite = (1) beam vs Euler-Bernoulli (analytical), (2) Laval TestCaseGeomertyMesh vs ANSYS+experiment (numerical+experimental). tistos runner is NOT a validation showcase. | DECIDED 2026-07-28 |
| 13 | Test strategy | **Characterization-First + tests-after** (user re-asked Q13, then picked recommended): freeze golden-reference tests from validated state (solver outputs, penalty/objective values, dtOO export, config roundtrip) BEFORE the move; existing validation suites (beam, Laval disc) keep running throughout as the primary net; new modules (optimizer backends, MCP, RL env) get tests-after; agent-executed QA (happy + failure path) on every todo. | DECIDED 2026-07-28 |
| 14 | Parallelization layer | **Native island model + evaluator-pool abstraction, no pygmo**: user directive "Parallelisierung einbauen wo möglich", concepts from ../de_framework but NOT bound to Pyro/pygmo. (a) Island-model topology native over the ask/tell Optimizer protocol: N subpopulations, independent evolve loops, periodic migration (ring, best-K, no-duplicate replacement policy — ported as concepts from de_framework start_de.py), JSON checkpoint+restart per island (archi_save.json pattern, aligned with existing de_state checkpoints); islands map to SLURM tasks (SLURM_NTASKS pattern). (b) EvaluatorPool interface: ProcessPool (local, existing) + Pyro5 RPC workers (existing server_de.py, preserved as ONE transport, interface not hardcoded to it). (c) pytest-xdist for validation suite. (d) Solver MPI (dolfinx) unchanged, documented. NO pygmo/pagmo dependency (heavy Boost C++ dep; island model is small over ask/tell). SLURM-array evaluator backend → Later TODO. | DECIDED 2026-07-28 |
| 15 | Branch strategy | **Branch `refactor/standalone-tool` from `main` HEAD e6f10cf** (re-decided 2026-07-28 after reopening): validated state incl. STL/Laval validation, de_history, cluster scripts lives on main; `cfd-eigenfreq-multiobjective` (d55c1d3, lacks those assets) stays untouched as history; no merge needed; no push/PR without explicit user request; merge-back policy decided later by user. Branch creation = todo 1. Original decision (base = feature branch) was falsified by post-approval verification. | DECIDED 2026-07-28 |
| 16 | Metis gap analysis | Post-approval Metis review (mandatory): verdict NEEDS-FIXES, 20 findings. ALL folds applied to the plan 2026-07-28: branch-base conflict (#1 → decision 15 reopened), pygmo in docker/fenicsx.Dockerfile + ci.yml removed in todo 40 / F4 grep extended (#4), optimize.py f_min/f_max field bug fixed on port in todo 10 (#9), import-time templateState.xml read removed, n_rpm required scalar in todos 7/14 (#10), keep/move table in todo 12 (#5), dtOO-case precondition in todos 22/23 (#6), Pyro5 test markers requires_dtoo/requires_slurm in todo 25 (#15), slepc4py pin parity + docker-as-QA-env note in todo 39 (#3), graphify-out untracking (git rm -r --cached, no history rewrite) in todo 42 (#13), stale docs/source API+quickstart refs in todo 41 (#14), tests/ layout+markers in todo 2, canonical golden source pinned in todo 3, deterministic-schema note in todo 15. Findings 7/8/11/12/16/17/18/20 already covered by existing todos. | FOLDED 2026-07-28 |
| 17 | High-accuracy review (user-triggered "deep review") | DUAL review 2026-07-28. RECEIPTS: (a) Momus (ses_054c5355effeCYLvJBHnU9eMSd): **[OKAY]** — plan executable as written, references verified, no blockers. (b) Oracle (ses_054c4e7d1ffe56GkZHvwu5siaq): **NEEDS-FIXES**, 10 findings — ALL verified against repo and folded: B1 config.py has 11 dataclasses not 8 (DesignConfig :176, OptimizationConfig :212, OutputConfig :370 added to todos 5+7 with real *Config names); B2 cluster/apptainer_fenicsx.def:18 pygmo added to todo 40 + F4 grep extended to cluster/; M1 island default SLURM_NTASKS→4 (islands=diversity, evaluator workers=SLURM_NTASKS — todo 26, TL;DR, F3, success criteria); M2 pycma→cma (PyPI name) in todo 28+TL;DR; M3 matrix todo 33 deps 24→7,19 + bounds source note; M4 CFDConfig.omega (:292) runtime-derived from n_rpm in todo 7 + acceptance assert; m1 requires-python >=3.11,<3.14 in todo 39; m2 ask+tell=generation semantics note in todo 26; m3 apptainer From: stable unpinned wording; m4 real class names. Oracle numerics verdict: freeze/compare strategy sound, MUMPS deterministic, 1e-4 tolerance safe — no findings. Review REQUIRED satisfied. | FOLDED 2026-07-28 |

## Approach (for approval)

ONE plan, full scope, dependency-ordered phases:

0. **Branch**: create `refactor/standalone-tool` from `cfd-eigenfreq-multiobjective` HEAD — all work on this branch.
1. **Characterization net**: golden-reference tests frozen from validated state (solver outputs, penalty/objective, dtOO export, config roundtrip); pytest-xdist for the validation suite.
2. **Package & refactor**: `turbine_runner/` → `src/eigenfrequencies/` (io/, solver/ generic clamped+free-free scipy+SLEPc, bc/, materials/, penalty/, added_mass/, validation/); `turbine_runner/` shrinks to thin dtOO project driver; validation suite green against new package.
3. **Tool interface**: YAML config + typer CLI (solve/validate/optimize/report) + JSON Schema export; cluster runs = config file + commit hash.
4. **dtOO adapter layer** (extra): declarative per-machine YAML (case dir, state, mech volume, adjust plugin, design labels+bounds, mesh scale factor, BC template); ships tistos + canadaLight + naca adapter YAMLs, each validated; canadaLight pre-check (solid/mech-volume state present?).
5. **Optimizer layer** (extra): Optimizer protocol (ask/tell); backends DE (custom, cluster+Pyro5 preserved), PSO (pymoo), CMA-ES (pycma), BO/TPE (optuna); **parallelization where possible**: native island-model topology (subpopulations + migration + per-island checkpoint/restart, concepts ported from ../de_framework, no pygmo dep), EvaluatorPool abstraction (ProcessPool local + Pyro5 as one transport of several, not hardcoded), islands↔SLURM tasks mapping; RL backend = generic gymnasium.Env over objective interface, SB3-compatible (PPO/SAC/TD3), offline-RL exporter de_history→d3rlpy; dry-modal first.
6. **MCP server** (extra): fastmcp stdio, job-based submit/poll/fetch, thin over same library API; resources = result JSONs + machine YAML catalog + curated domain docs; NO code-knowledge tools (graphify's job).
7. **Graph/LLM knowledge**: mandatory `graphify update` post-refactor + docs/validation corpus ingest.
8. **Distribution & docs**: public repo prep, environment.yml (conda-forge fenics-dolfinx+slepc4py), Dockerfile refresh, install docs (conda env create → `uv pip install . --no-deps`); no PyPI.
9. **Final verification wave**: validation suites green, 3 adapters validated, CLI end-to-end, MCP smoke test, docs complete.

Must-NOT-have: wet-mode/FSI, NSGA-II, ACO, HippoRAG, Figma/code-connect UI, config UI, PyPI release, PBO adoption, MCP code-knowledge tools, CFD-coupling rewrite (stays project code), pygmo/pagmo dependency, SLURM-array evaluator backend (Later TODO), work directly on `cfd-eigenfreq-multiobjective` (all on `refactor/standalone-tool`), any MVP/phase-1 scope reduction.

## Next workflow action

Plan `.omo/plans/eigenfrequencies-final-design.md` FINAL and REVIEWED: approved 2026-07-28; Metis folds applied; decision 15 re-decided (branch from main HEAD e6f10cf); dual high-accuracy review complete (Momus [OKAY], Oracle NEEDS-FIXES → all 10 findings verified + folded; receipts in decision 17). Structural self-check passed (42 + F1–F4). Handoff brief delivered. PENDING: user starts execution via `$start-work` (options --worktree/--make-pr/--ship). Never execute in this session.

## Later TODO list (user-requested, out of plan scope)

- dtOO introspection tooling: adapter reads dtOO constValues/dtLattice, proposes design params + bounds for confirmation (from Q5 option 2).
- Visual config editor: schema-generated web form (react-jsonschema-form) from the exported JSON Schema — testcase dropdown, include_cfd toggle, optimizer/worker binding (from Q10; Figma-based variant explicitly rejected after research).
- SLURM-array evaluator backend: sbatch-array-based evaluation transport as alternative to Pyro5 workers (from decision 14).

## Question log

- Q1 2026-07-28 ✔ Kern + optionale Layer (as recommended).
- Q2 2026-07-28 ✔ Ein Paket `src/eigenfrequencies/`, turbine_runner wird dünner dtOO-Driver (as recommended).
