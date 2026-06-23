# Project Documentation — Eigenfrequencies as a Shape-Optimization Objective

Living progress record for the project report. Append-only by milestone; newest at top.

## 1. Goal

Extend dtOO-driven Francis-runner **shape optimization** (classic hydraulic objectives:
efficiency, cavitation volume, design head) with a **structural eigenfrequency objective**
to avoid resonance. Long-term: couple to fluid–structure interaction (FSI). Near-term:
use only the **static** pressure field and the dry/wet structural modes.

## 2. Physics rationale (decided)

- **A static fluid has no resonance of its own.** Resonance needs time-varying excitation;
  a steady pressure field is a constant load and cannot excite it.
- The static fluid still matters two ways, **without unsteady CFD**:
  1. **Added mass** — still water lowers the *wet* eigenfrequencies 20–40 % vs *dry*
     (in-vacuo); geometry-dependent, so it matters during shape optimization.
  2. **Pre-stress** — the mean pressure load slightly shifts frequencies (minor).
- **Excitation frequencies are kinematic** — blade-passing `Z_guidevanes · n`, harmonics,
  diametral-mode matching. Known from vane count + rpm, no CFD needed. Resonance avoidance =
  keep (eventually wet) eigenfrequencies out of those bands.
- **FSI** (Helmholtz-acoustic ↔ elasticity) is the later extension; it adds the forced-response
  **amplitude** (how severe a resonance is), not whether one occurs.
- Naming: it is the **Helmholtz** equation (acoustic), not Gibbs–Helmholtz (thermodynamics).

## 3. Design decisions

| # | Decision | Rationale |
|---|----------|-----------|
| a | Eigenfrequency objective enters as a **constraint/penalty**, not a separate Pareto axis | Keeps the hydraulic objective space low-dimensional; resonance only bites on violation |
| b | **Dry modes now, wet (added-mass) modes later**, with parallel dry-vs-wet comparison | Dry solve already validated; added mass is the next physical correction |
| — | **Fixed Hz forbidden band now**, kinematic blade-passing band later | Fastest path to a working objective; band source upgraded once vane count + rpm wired |
| — | Build in the **eigenfrequencies** repo; de_framework is a **reference** (reuse patterns/CFD math, do not branch it) | de_framework "worked" but need not be used as-is |
| — | dolfinx on the cluster via **apptainer** (not yet provisioned) | dtOO+OpenFOAM and FEniCSx are disjoint stacks |

## 4. Architecture

Per design vector `x` (dtOO const-value params):

```
x ──dtOO──┬─► OF case dir ──simpleFoam(steady)─► η, Vcav, dH      (cfd_eval.evaluate_cfd)
          └─► runner.msh   ──RunnerModalSolver──► dry eigenfreqs   (solver / evaluate.py)
                                                  └─wet (added mass, deferred)
objective = w_eta·tanh(|1+η|) + w_cav·tanh(Vcav·1e6) + w_head·tanh(|dH−dH_zul|)
            + w_res·resonance_penalty           # constraint term, 0 unless mode in band
```

CFD math + `tanh` scalarization ported from de_framework `tistos_files/tistosPyBib.py`.

## 5. Status

### Done (this milestone) — locally implemented, dry path validated end to end previously
- `config.py`: `CFDConfig`, `ObjectiveConfig`, `WetModeConfig` added.
- `objective.py` (new): `cfd_scalar`, `resonance_term`, `combined_objective` (CFD + resonance).
- `cfd_eval.py` (new): OpenFOAM `postProcessing` reader → η, Vcav, dH, P, Q (no pyDtOO/dolfinx).
- `added_mass.py` (new): wet-mode interface + `wet_from_ratios` + placeholder ratios; Laplace solve stubbed.
- `solver.py`: `wet_compare()` method (dry-vs-wet, non-breaking).
- `optimize_multi.py` (new): host orchestrator, CFD optional (degrades to resonance-only).
- `cluster/`: `submit.sh` (SLURM), `apptainer_fenicsx.def`, `env_notes.md`.
- Pre-existing & reused: `solver.py` dry modal, `optimization.py` forbidden-band penalty,
  `dtoo_export.py` mech mesh, `mesh_prep.py`, `evaluate.py`.

### Pending — cluster (handoff)
- Provision dolfinx via apptainer on bwUniCluster 3.0.
- Build the dtOO **OF CFD case** from the same state as the mech mesh (extend `dtoo_export.py` /
  port de_framework `createStatesAndMeshes.CreateMeshes`).
- Validate `cfd_eval.py` column indices against real `postProcessing/` output.
- Run `simpleFoam` objectives live; full multi-node parallel optimization.

### Pending — physical validation (carried from turbine_runner memory)
1. **Mesh units** — dtOO coords scaled (~2.5 bbox, not metres) → rescales every Hz and the band.
2. **Hub-clamp BC** physicality (confirm in ParaView).
3. **P1 vs P2** stiffness (P2 OOMs on small hosts).
4. No near-zero rigid-body modes (clamp check already passes).
5. Implement `added_mass.rayleigh_ratios` (replace placeholder) and confirm wet < dry.

## 6. Later (out of current scope)

Unsteady CFD; Helmholtz-acoustic ↔ elasticity FSI; forced-response amplitude/fatigue;
kinematic blade-passing band auto-derivation; true multi-objective Pareto (NSGA-II) if the
scalarization proves limiting.
