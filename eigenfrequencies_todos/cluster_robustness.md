---
status: partial
scope: cluster stability, mesh/BC calibration, future async-DE — folds known issues + open infra tasks
related_files:
  - turbine_runner/optimize.py (`_run_dtoo`, `_run_fenicsx`, `_run_cfd`)
  - turbine_runner/mesh_prep.py
  - turbine_runner/solver.py (hub clamp)
  - turbine_runner/config.py (`MeshConfig`, `BCConfig`, `SolverConfig`)
  - de_framework (reference for pygmo async-DE pattern)
detail_of: "[[obsidian_dashboard_eigenfrequencies#4. Cluster robustness hardening]]"
---

# Cluster robustness hardening

Cross-cutting cluster concerns. Currently partial: cluster runs, but a hung container can block a generation; mesh units + hub-clamp BC physicality still open.

## Sub-items

- [ ] Subprocess timeout on `_run_dtoo` (mirror `_run_cfd` 1800s default; tune per env)
- [ ] Subprocess timeout on `_run_fenicsx`
- [ ] Per-generation wall-clock guard (watchdog / cancel-all on stuck worker)
- [ ] Mesh units calibration: run `mesh_prep.py` axis-discovery on cluster, compute physical scale factor, rescale Hz + band edges
- [ ] Hub-clamp BC physicality: ParaView confirm no near-zero rigid-body modes; fix BC if spurious modes appear
- [ ] Document async steady-state DE design (rolling dispatch, like de_framework pygmo archipel) — implementation NOT desired by user, only documented

## Known issues (informational)

- Sync-DE barrier → straggler-tail (fast workers idle until slowest finishes) + thundering herd at gen start (many containers / simpleFoam spawn concurrently). Higher `cpus-per-task` shifts balance but does not eliminate.
- Per-worker container spin-up cost dominates short evals; persistent Pyro5 workers already in place — shared mesh cache is a stretch goal.

## Reference

- HANDOFF §5 (timeouts, async DE, CFD-Ressourcen caveat)
- Dashboard Known Bugs history (ThreadPoolExecutor deadlock — fixed; rayleigh_ratios NIE — open; cluster pipeline — verified for resonance)

## Context from obsidian_eigenfrequencies.md

### Quick Status (robustness-related)

| Component | Status | Last Test | Notes |
|-----------|--------|-----------|-------|
| **Mesh units calibration** | 🟡 Open | — | dtOO coords scaled (~2.5 bbox, not metres) → rescales every Hz and the band |
| **Hub-clamp BC physicality** | 🟡 Open | — | Confirm clamped-node bbox at hub in ParaView (`output/modes.xdmf`) |
| **P1 vs P2 convergence** | 🟡 Open | — | P2 (`SolverConfig.element_degree=2`) more accurate, ~1M DOFs → OOM on <8 GB hosts |

### Open Tasks

- [ ] **Mesh units calibration** `priority::high`
  - dtOO coords scaled (~2.5 bbox, not metres) → rescales every Hz and the band
  - Measure physical runner dims, compute scale factor, update `config.py` and `BCConfig`

- [ ] **Hub-clamp BC physicality** `priority::high`
  - Confirm clamped-node bbox at hub in ParaView (`output/modes.xdmf`)
  - If near-zero rigid-body modes appear → fix `BCConfig` (axis, hub_radius, plane_value)

### Known Problems

1. **Mesh units unknown** — dtOO coords are scaled (~2.5 bbox). Frequencies and band positions may need rescaling once physical dimensions are known. Band formula (Z·n/60) is correct, but absolute Hz values depend on mesh scale.
2. **P2 OOM risk** — `SolverConfig.element_degree=2` ~1M DOFs on cluster node may exceed memory if `dev_cpu` node is small.
3. **No near-zero rigid-body modes locally** — clamp passes locally; physicality confirmation (ParaView) still TODO.
