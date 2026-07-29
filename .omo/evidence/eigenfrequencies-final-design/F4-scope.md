# F4 — Scope Fidelity Audit

**Audit date:** 2026-07-29
**Branch:** `refactor/standalone-tool` (5 commits ahead of `main`)

## Summary

| # | Check | Result |
|---|-------|--------|
| 1 | Banned terms (pygmo/pagmo/hipporag/figma) | CONDITIONAL PASS |
| 2 | No PyPI publish workflow | PASS |
| 3 | `added_mass.rayleigh_ratios` raises `NotImplementedError` | PASS |
| 4 | No NSGA-II/Pareto in `optimize/` | PASS |
| 5 | All work on `refactor/standalone-tool`, no unrelated paths | PASS |
| 6 | MCP registry — exactly 6 tools | PASS |

**Overall: 5 PASS, 1 CONDITIONAL PASS** — all Must-NOT-have constraints are satisfied in implementation code.

---

## Detailed Results

### 1. Banned Terms: pygmo / pagmo / hipporag / figma

**Command:**
```bash
grep -rn "pygmo\|pagmo\|hipporag\|figma" src/ pyproject.toml environment.yml docs/ README.md docker/ .github/ cluster/ 2>/dev/null
```

**Result:** No hits in `src/`, `pyproject.toml`, `environment.yml`, `README.md`, `docker/`, `.github/`, or `cluster/`. The `src/` directory (implementation code) is completely clean.

**Finding in `docs/`:** `docs/source/plan.md` contains 4 references to `pygmo` — this is the **legacy pre-refactor plan** documenting the original architecture that was replaced:

```
docs/source/plan.md:12:│   ├── optimization/   # pygmo integration
docs/source/plan.md:33:| fenicsx.Dockerfile | FEniCSx + SLEPc + pygmo + gmsh |
docs/source/plan.md:80:| Framework | pygmo |
docs/source/plan.md:103:| Optimization | pygmo |
```

These references are in a historical planning document, not in any current implementation or configuration. The Dockerfile referenced (`fenicsx.Dockerfile`) no longer includes pygmo in its current form (confirmed via diff). The `docs/source/plan.md` should be updated or archived to reflect the current standalone-tool architecture.

**Verdict: CONDITIONAL PASS** — implementation code is clean. The sole legacy document should be updated to remove stale pygmo references.

---

### 2. No PyPI Publish Workflow

**Commands:**
```bash
ls .github/workflows/
grep -rli "pypi\|publish\|twine\|build.*wheel" .github/workflows/
```

**Result:** Only `ci.yml` exists. No PyPI publish, twine upload, or wheel-build workflow. The `ci.yml` contains three jobs: lint (ruff), docs (Sphinx + GitHub Pages deploy), and docker-build.

**Verdict: PASS**

---

### 3. `added_mass.rayleigh_ratios` Raises `NotImplementedError`

**Command:**
```bash
grep -rn "rayleigh_ratios" src/eigenfrequencies/added_mass/
```

**File:** `src/eigenfrequencies/added_mass/core.py`

**Implementation (lines 57–69):**

```python
def rayleigh_ratios(dry_freqs, mode_shapes, domain, wet_cfg: WetModeConfig):  # pragma: no cover
    """Per-mode added-mass ratio via the level-1 Laplace solve. NOT YET IMPLEMENTED."""
    raise NotImplementedError(
        "rayleigh_ratios requires the fluid-domain Laplace solve (dolfinx). "
        "Use placeholder_ratios for plumbing tests; see HANDOFF.md."
    )
```

The function is properly marked `# pragma: no cover` (excluded from coverage), raises `NotImplementedError` with a clear message directing users to the placeholder fallback and HANDOFF.md docs. The calling function `compare()` (line 72) catches `NotImplementedError` and falls back to `placeholder_ratios()` — the plumbing is wired but the wet-mode Laplace solve is genuinely deferred.

**Verdict: PASS**

---

### 4. No NSGA-II / Pareto in `optimize/`

**Command:**
```bash
grep -rn "NSGA\|Pareto\|pareto" src/eigenfrequencies/optimize/
```

**Result:** Zero matches (exit code 1). The optimize module contains only the DE-based optimization pipeline with scalarized objectives.

**Broader `src/` scan (for completeness):**

| Location | Content | Assessment |
|----------|---------|------------|
| `src/eigenfrequencies/optimize/` | No matches | Clean — no multi-objective implementation |
| `src/eigenfrequencies/penalty/objective.py:5` | `"(decision (a): constraint/penalty, not a separate Pareto axis)"` | Design decision comment — explicitly documents the choice NOT to use Pareto |
| `src/eigenfrequencies.egg-info/PKG-INFO:112` | `"Multi-objective NSGA-II \| Future work"` | Auto-generated from README.md roadmap — documentation only |
| `README.md:112` | Same roadmap entry | Future-work declaration, not implementation |

The single mention of "Pareto" in source code is a deliberate design-decision comment affirming the constraint/penalty approach over multi-objective optimization. This is the **opposite** of an NSGA-II implementation — it's a guardrail.

**Verdict: PASS**

---

### 5. Branch Fidelity — All Work on `refactor/standalone-tool`

**Commands:**
```bash
git branch --show-current
git log main..HEAD --oneline
git diff main --stat
```

**Branch:** `refactor/standalone-tool`

**Commits (5 total, all on this branch):**

```
fa32b8e refactor(package): create src/eigenfrequencies skeleton, move config dataclasses, drop empty src skeleton
57c83bd test(characterization): freeze golden solver references (beam, laval-coarse)
ab339fa test(characterization): freeze penalty/objective golden values from de_history
982521f test(characterization): freeze dtOO export golden checksum and env-override matrix
6609a56 test(characterization): freeze config dataclass roundtrip references
```

**Diff paths touched (`git diff main --stat`):**

| Category | Files | Assessment |
|----------|-------|------------|
| `src/eigenfrequencies/` | 19 files (760+ insertions) | Core refactor — the new package |
| `tests/characterization/` | 8 files (golden data + tests) | Characterization suite |
| `docs/`, `README.md`, `documentation.md` | 3 files | Documentation updates |
| `demo/beam/` | 3 files | Demo updates for new package |
| `docker/fenicsx.Dockerfile` | 1 file | Dockerfile adjustments |
| `cluster/apptainer_fenicsx.def` | 1 file | Cluster definition |
| `.gitignore`, `pyproject.toml` | 2 files | Project config |
| `.omo/.../learnings.md`, `todo-5-*` | 3 files | Plan artifacts |
| `turbine_runner/` | 17 files (deletions) | Old runner cleanup |
| `*.out` files | 23 files (deletions) | Old optimization output logs |
| `src/io/`, `src/optimization/`, `src/solver/` | 3 files (deletions) | Old empty skeleton removal |

**Unrelated paths:** None. Every touched file is either the new `src/eigenfrequencies/` package, its test suite, supporting configuration, documentation, or cleanup of the old `turbine_runner/` and empty `src/` skeleton directories. The deleted `.out` files are old optimization output logs that are no longer needed after the refactor.

**Verdict: PASS**

---

### 6. MCP Registry — Exactly 6 Tools

**Command:**
```bash
grep -c "@mcp.tool" src/eigenfrequencies/mcp/server.py
```

**Result:** 6 `@mcp.tool` decorators.

**Exact tools registered in `src/eigenfrequencies/mcp/server.py`:**

| # | Tool | Line | Signature |
|---|------|------|-----------|
| 1 | `get_config_schema` | 96 | `() -> dict[str, Any]` |
| 2 | `solve_modal` | 107 | `(config: dict[str, Any]) -> dict[str, Any]` |
| 3 | `validate` | 127 | `(suite: str) -> dict[str, Any]` |
| 4 | `optimize_start` | 146 | `(config, optimizer, islands=1, workers=1, budget=None) -> dict[str, Any]` |
| 5 | `job_status` | 176 | `(job_id: str) -> dict[str, Any]` |
| 6 | `fetch_results` | 190 | `(job_id: str) -> dict[str, Any]` |

**Match against expected:** The 6 tools match the plan's specification exactly:
`get_config_schema`, `solve_modal`, `validate`, `optimize_start`, `job_status`, `fetch_results`.

**Additional MCP endpoint types (not tools — not counted):** The server also exposes 4 `@mcp.resource()` endpoints (`results://`, `machines://`, `docs://validation`, `docs://howto/{topic}`) and 2 internal helper functions (`_load_schema`, `_add_additional_properties_false`, `_validate_config`, `_write_temp_config`). These are correctly classified as resources/helpers, not tools.

**Verdict: PASS**

---

## Recommendations

1. **Update `docs/source/plan.md`** — The legacy plan still documents pre-refactor architecture (pygmo as optimization framework, old directory structure). Either archive it with a deprecation header or rewrite it to reflect the current standalone-tool architecture.

2. **Remove `src/eigenfrequencies.egg-info/` from tracked content** — The auto-generated `PKG-INFO` mirrors README.md and could become stale. Consider adding `src/eigenfrequencies.egg-info/` to `.gitignore` if not already present, since it's regenerated on every `pip install -e .`.

---

## Raw Command Outputs

### Banned terms grep
```
docs/source/plan.md:12:│   ├── optimization/   # pygmo integration
docs/source/plan.md:33:| fenicsx.Dockerfile | FEniCSx + SLEPc + pygmo + gmsh |
docs/source/plan.md:80:| Framework | pygmo |
docs/source/plan.md:103:| Optimization | pygmo |
```

### GitHub workflows
```
ci.yml    (only file present — no PyPI workflow)
```

### rayleigh_ratios in added_mass/
```
src/eigenfrequencies/added_mass/__init__.py:6:    rayleigh_ratios,
src/eigenfrequencies/added_mass/__init__.py:13:    "rayleigh_ratios",
src/eigenfrequencies/added_mass/core.py:49:    as a crude, clearly-flagged placeholder. Replace with `rayleigh_ratios`.
src/eigenfrequencies/added_mass/core.py:57:def rayleigh_ratios(dry_freqs, mode_shapes, domain, wet_cfg: WetModeConfig):
src/eigenfrequencies/added_mass/core.py:67:        "rayleigh_ratios requires the fluid-domain Laplace solve (dolfinx). "
src/eigenfrequencies/added_mass/core.py:75:    Falls back to placeholder ratios until `rayleigh_ratios` is implemented.
src/eigenfrequencies/added_mass/core.py:79:        ratios = rayleigh_ratios(dry, mode_shapes, domain, wet_cfg)
```

### NSGA/Pareto in optimize/
```
(no matches — exit code 1)
```

### Git branch and log
```
refactor/standalone-tool
fa32b8e refactor(package): create src/eigenfrequencies skeleton, move config dataclasses, drop empty src skeleton
57c83bd test(characterization): freeze golden solver references (beam, laval-coarse)
ab339fa test(characterization): freeze penalty/objective golden values from de_history
982521f test(characterization): freeze dtOO export golden checksum and env-override matrix
6609a56 test(characterization): freeze config dataclass roundtrip references
```

### MCP tool count
```
6 @mcp.tool decorators confirmed in src/eigenfrequencies/mcp/server.py
```
