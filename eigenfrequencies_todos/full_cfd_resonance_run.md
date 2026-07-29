---
status: blocked_by_cfd_smoke
scope: production multi-objective DE — full CFD + resonance on multi-node cpu partition
related_files:
  - turbine_runner/optimize_de.py
  - turbine_runner/server_de.py
  - turbine_runner/dtoo_cfd_build.py
  - turbine_runner/cfd_eval.py
  - cluster/submit_de.sh
  - cluster/submit.sh
detail_of: "[[obsidian_dashboard_eigenfrequencies#3. Full CFD + resonance production run]]"
---

# Full CFD + resonance production run

Sequence after cfd smoke passes. CFD-bearing objectives cannot scale until column mapping is trusted.

## Sub-items

- [ ] Tune `cpus-per-task` for simpleFoam MPI per worker (current dev_cpu_il 30 min insufficient for prod)
- [ ] Scale `cpu` partition: more nodes, longer walltime (`--time=72:00:00` if available)
- [ ] Increase `DE_POP_SIZE` and `DE_MAX_GEN` for production convergence
- [ ] Validate eta/vcav/dH sanity bounds before trusting optima
- [ ] Verify checkpoint resume across the longer (multi-day) runtime
- [ ] If scalarization limits progress → fallback to NSGA-II (see [[eigenfrequencies_todos/phase4_deferred]])

## Reference

- HANDOFF §2 / §6 (full-lauf follows smoke), §5 (CFD-Ressourcen partition caveat)

## Context from obsidian_eigenfrequencies.md

### Experiment Tracking

| Experiment | Status | Config | Result | Notes |
|-----------|--------|--------|--------|-------|
| Cluster batch (full CFD+res) | 🔴 Planned | `sbatch cluster/submit.sh` + OF case dir | — | After CFD case build |
