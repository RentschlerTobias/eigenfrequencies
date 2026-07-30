# F1 — Plan Compliance Audit

Generated: 2026-07-29.  
Plan: `.omo/plans/eigenfrequencies-final-design.md` (42 todos, waves 1–8).

## Summary

| Status     | Count |
|------------|-------|
| APPROVE    | 24    |
| DEVIATION  | 18    |
| **Total**  | **42** |

Of the 18 deviations, 14 are **missing evidence files** and 4 have **partial evidence** (happy only or precheck only). All source-level deliverables exist in the repo for every todo — no todo is entirely unimplemented. The learnings file (`.omo/notepads/eigenfrequencies-final-design/learnings.md`) documents test-pass counts and key findings for todos 8, 9, 12, 14, 15, 18, 20, 26, partly filling the evidence gap.

---

## Compliance Table

| # | Status | Evidence Path(s) | Notes |
|---|--------|------------------|-------|
| 1 | APPROVE | `todo-1-happy.log` (530 B), `todo-1-failure.log` (442 B) | Branch `refactor/standalone-tool` at e6f10cf. Both logs contain recorded commands + output. |
| 2 | APPROVE | `todo-2-happy.log` (524 B), `todo-2-failure.log` (15.7 KB) | Golden JSONs committed: `beam.json`, `testcase_coarse.json` (29 MB), `tistos_coarse.json`. Tests pass. |
| 3 | APPROVE | `todo-3-happy.log` (2.2 KB), `todo-3-failure.log` (223 B) | `objective_cases.json` committed. 6 passed. Replay within rel. 1e-9. |
| 4 | APPROVE | `todo-4-happy.log` (3.5 KB), `todo-4-failure.log` (5.0 KB) | `dtoo_export.json` committed. dtOO unavailable locally — 7 skipped with clear message. |
| 5 | APPROVE | `todo-5-happy.log` (1.0 KB), `todo-5-failure.log` (632 B) | `config_roundtrip.json` committed. 11 dataclass roundtrips pass. |
| 6 | APPROVE | `todo-6-happy.log` (1.6 KB), `todo-6-failure.log` (3.2 KB) | pytest-xdist configured in `pyproject.toml`. Marker policy in `tests/README.md`. |
| 7 | APPROVE | `todo-7-happy.log` (1.3 KB), `todo-7-failure.log` (1.1 KB) | Package skeleton created. 11 config dataclasses moved, import-time filesystem dependency removed. |
| 8 | DEVIATION | **No evidence files** | Source: `solver/{core,scipy_backend,slepc_backend,rayleigh,exceptions}.py` exist. Learnings.md: 5 passed in ~19 s. QA log files not written. |
| 9 | DEVIATION | **No evidence files** | Source: `io/{load,axis,results,stl_to_msh,cfd_eval}.py` exist. Learnings.md: 1 passed, 2 skipped (container-only). QA log files not written. |
| 10 | APPROVE | `.omo/notepads/.../todo-10-happy.log` (6.2 KB), `.omo/notepads/.../todo-10-failure.log` | Source: `bc/`, `materials/`, `penalty/`, `added_mass/` exist. 33 passed. Evidence in notepads (non-standard location). |
| 11 | APPROVE | `.omo/notepads/.../todo-11-happy.log` (1.4 KB), `.omo/notepads/.../todo-11-failure.log` | Source: `validation/{beam,testcase}/` exist. Learnings.md: 2 skipped locally, 1 passed + 1 skipped in container. Evidence in notepads. |
| 12 | DEVIATION | **No evidence files** | Source: `turbine_runner/` thinned to driver-only. 12 modules deleted, `legacy/` created. Learnings.md: 46 passed, 12 skipped. QA log files not written. |
| 13 | APPROVE | `todo-13-happy.log` (154 B), `todo-13-failure.log` (223 B), `todo-13-module-map.md` (5.7 KB) | All characterization tests green. Module map documents old→new paths. |
| 14 | DEVIATION | **No evidence files** | Source: `config_yaml.py` exists. 6 example YAMLs in `examples/configs/`. Learnings.md: 11 passed in 1.05 s. QA log files not written. |
| 15 | DEVIATION | **No evidence files** | Source: `schema.py` exists. `schema/eigenfrequencies-config.schema.json` committed. Learnings.md: 21 passed in 1.00 s. QA log files not written. |
| 16 | APPROVE | `todo-16-happy.log` (3.9 KB), `todo-16-failure.log` (5.0 KB) | CLI `solve` + `validate` subcommands exist. 19 passed. Solve prints frequencies; validate exits 0/4. |
| 17 | APPROVE | `todo-17-happy.log` (2.6 KB), `todo-17-failure.log` (3.5 KB) | CLI `optimize` + `report` subcommands exist. 33 passed (all CLI tests). |
| 18 | DEVIATION | **No evidence files** | Source: `provenance.py` exists. Learnings.md: 17 passed in ~1 s. CLI wired into solve + optimize. QA log files not written. |
| 19 | APPROVE | `todo-19-happy.log` (774 B), `todo-19-failure.log` (85 B) | Adapter core + machine YAML schema exist. 25 passed in 2.10 s. |
| 20 | DEVIATION | **No evidence files** | Source: CLI `dtoo discover-axis` + `measure-scale` exist. Learnings.md: 11 passed in 5.17 s. QA log files not written. |
| 21 | DEVIATION | **No evidence files** | Source: `adapters/machines/tistos.yaml` exists. Todo 4 golden checksum provides parity baseline. This todo requires dtOO container for full verification; no QA log files written. |
| 22 | DEVIATION | `todo-22-happy.log` (2.1 KB), `todo-22-precheck.md` (5.1 KB) | `canadaLight.yaml` exists. Precheck answers solid-volume/design-label questions. Missing `todo-22-failure.log`. |
| 23 | DEVIATION | `todo-23-precheck.md` (3.7 KB) only | `naca.yaml` exists. Precheck documents foil-clamp BC setup. Missing `todo-23-happy.log` and `todo-23-failure.log`. |
| 24 | APPROVE | `todo-24-happy.log` (774 B), `todo-24-failure.log` (64 B) | Optimizer protocol + DE backend exist. 24 passed in 2.07 s. |
| 25 | APPROVE | `todo-25-happy.log` (8.8 KB), `todo-25-failure.log` (1.8 KB) | EvaluatorPool (ProcessPool + Pyro5) exists. 31 passed, 1 skipped (Pyro5 absent). |
| 26 | DEVIATION | **No evidence files** | Source: `optimize/islands.py` (523 LOC, SIZE_OK documented). Learnings.md: 27 passed in ~5 s, 51 full suite. No QA log files written. |
| 27 | APPROVE | `todo-27-happy.log` (4.0 KB), `todo-27-failure.log` (111 B) | PSO backend (pymoo) exists. 15 passed in ~4 s. |
| 28 | APPROVE | `todo-28-happy.log` (4.3 KB), `todo-28-failure.log` (1.3 KB) | CMA-ES backend (cma) exists. 11 passed in ~2 s. |
| 29 | APPROVE | `todo-29-happy.log` (1.1 KB), `todo-29-failure.log` (346 B) | BO/TPE backend (optuna) exists. 12 passed in ~3 s. |
| 30 | DEVIATION | `todo-30-happy.log` (1.2 KB) only | Conformance suite: 48 passed. Beam-spline integration: all 4 backends clear forbidden band (penalty 641→0). Missing `todo-30-failure.log`. |
| 31 | DEVIATION | **No evidence files** | Source: `optimize/rl/env.py` (166 LOC) exists. Todo 32 depends on this and has evidence. No standalone QA log files for env. |
| 32 | DEVIATION | `todo-32-happy.log` (2.0 KB) only | SB3 smoke: PPO/SAC/TD3 construct. DQN rejection works (exit 2). SB3 absent locally → 1 skipped. Missing `todo-32-failure.log`. |
| 33 | APPROVE | `todo-33-happy.log` (785 B), `todo-33-failure.log` (327 B) | Offline-RL exporter exists. 28 passed, 2 skipped (d3rlpy absent). Corrupt-line handling verified. |
| 34 | APPROVE | `todo-34-happy.log` (774 B), `todo-34-failure.log` (773 B) | Job manager exists. 23 passed in 1.68 s. JobNotFoundError verified. |
| 35 | APPROVE | `todo-35-happy.log` (3.0 KB), `todo-35-failure.log` (311 B) | FastMCP server with 6 tools exists. 21 passed in 0.6 s. Config validation rejects typos. |
| 36 | APPROVE | `todo-36-happy.log` (774 B), `todo-36-failure.log` (5.5 KB) | MCP resources (4) + guardrails exist. 18 passed. Probe tool caught by registry-shape test. |
| 37 | APPROVE | `todo-37-happy.log` (741 B), `todo-37-failure.log` (2.1 KB) | MCP stdio e2e smoke: 4 passed, 1 skipped. Full flow (schema→solve→poll→fetch) works in container. |
| 38 | APPROVE | `todo-38-happy.log` (3.2 KB), `todo-38-failure.log` (893 B) | Graphify updated. 14195 nodes, 28716 edges, 803 communities. Queries return new module paths. RunnerModalSolver returns only docs. |
| 39 | DEVIATION | **No evidence files** | Source: `environment.yml` exists. `pyproject.toml` has `[project.optional-dependencies]` with optimize/rl/mcp/dtoo/dev extras. `requires-python = ">=3.11,<3.14"`. No QA log files. |
| 40 | DEVIATION | **No evidence files** | Source: `docker/fenicsx.Dockerfile` exists. No pygmo/pagmo references. No QA log files written. |
| 41 | DEVIATION | **No evidence files** | Source: `docs/{install,quickstart,adapters,mcp,cluster}.md` exist. No QA log files (quickstart walkthrough not recorded). |
| 42 | DEVIATION | **No evidence files** | Source: `LICENSE` (MIT) exists. `README.md` updated. `.gitignore` has proper entries. `graphify-out/` clean (not tracked). No QA log files (secrets sweep not recorded). |

---

## Cross-Cutting Checks

| Check | Result |
|-------|--------|
| Branch = `refactor/standalone-tool` | ✅ confirmed |
| No `pygmo`/`pagmo` in `pyproject.toml`, `docker/`, `cluster/` | ✅ clean (exit 1 on grep) |
| No `f_min`/`f_max` legacy field names in `src/eigenfrequencies/` | ✅ clean |
| No tistos/runner names in `src/eigenfrequencies/solver/` | ✅ clean |
| `turbine_runner/legacy/` exists | ✅ confirmed |
| 3 machine YAMLs committed | ✅ `tistos.yaml`, `canadaLight.yaml`, `naca.yaml` |
| 6 example config YAMLs | ✅ `beam`, `testcase_laval`, `tistos`, `minimal`, `default`, `custom` |
| JSON Schema committed | ✅ `schema/eigenfrequencies-config.schema.json` |
| 6 MCP tools (exactly) | ✅ confirmed by todo-35/36/37 evidence |
| 5 optimizer backends registered | ✅ de, pso, cmaes, bo + protocol |
| `environment.yml` exists | ✅ |
| `LICENSE` (MIT) exists | ✅ |
| `docs/` with 5 files | ✅ install, quickstart, adapters, mcp, cluster |
| Golden JSONs: beam, testcase_coarse, tistos_coarse | ✅ all committed |
| Characterisation tests import from `eigenfrequencies.*` only | ✅ confirmed by todo-13 module map |
| Graphify returns new module paths | ✅ confirmed by todo-38 queries |
| `graphify-out/` not tracked | ✅ clean |
| No pygmo/pagmo in `docker/fenicsx.Dockerfile` or `cluster/apptainer_fenicsx.def` | ✅ clean |

---

## Deviation Breakdown

### A. Missing Evidence Files — Source Code Exists (14 todos)

Todos **8, 9, 12, 14, 15, 18, 20, 21, 26, 31, 39, 40, 41, 42** have no QA evidence files (happy.log / failure.log) under `.omo/evidence/`. The learnings file documents build success and test-pass counts for 8 of these (8, 9, 12, 14, 15, 18, 20, 26). For the remaining 6 (21, 31, 39, 40, 41, 42), only source-level deliverable existence can be confirmed.

### B. Partial Evidence — Happy or Precheck Only (4 todos)

- **Todo 22**: `happy.log` + `precheck.md` exist; `failure.log` absent.
- **Todo 23**: Only `precheck.md` exists; neither `happy.log` nor `failure.log`.
- **Todo 30**: `happy.log` exists (penalty trajectory table + 144 passed); `failure.log` absent.
- **Todo 32**: `happy.log` exists (SB3 smoke + DQN rejection); `failure.log` absent.

### C. Non-standard Evidence Location (2 todos)

- **Todos 10, 11**: Evidence files exist under `.omo/notepads/eigenfrequencies-final-design/` instead of the expected `.omo/evidence/eigenfrequencies-final-design/`. Content is valid (contains recorded command output). Rated APPROVE with location note.

---

## Conclusion

24 of 42 todos (57%) have complete evidence per the plan's QA requirements. 18 todos (43%) deviate — all due to missing or partial QA log files, not due to missing implementation. Every todo's source-level deliverables (modules, YAMLs, schemas, docs, configs) are present in the repo. No todo is unimplemented.
