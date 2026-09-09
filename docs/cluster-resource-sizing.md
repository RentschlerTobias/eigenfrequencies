# Resource sizing for the tistos production runs

**Status:** 2026-09-09, branch `fix/bwuni-enroot-hardening`
**Purpose:** record what was measured on bwUniCluster 3.0, what was decided from
it, and what is still an estimate — so the 48-hour production runs are sized by
data rather than by intuition, and so a later reader can tell the two apart.

Written after the freq and combined chains ran end to end for the first time.
Everything before this document was blocked on three defects in the dtOO export
path; they are listed in section 6 because they explain why no such measurement
existed until now.

---

## 1. The measurements

All from `dev_cpu_il` (64 cores, 256 GiB), 30-minute slots, with the dev configs
`cluster/configs/tistos-*-dev.toml`. Per-stage seconds come from `timings` in
each `evaluations/<id>/outcome.json` and are printed by
`cluster/summarize_run.py`.

### 1.1 Modal chain — `tistos-freq-only-dev`, job 6843923

Five candidates, five successes, no failures.

| Stage | Seconds (mean of 5) |
|---|---|
| `mesh` (dtOO export, single-threaded gmsh) | 304.5 |
| `modal` (SLEPc/MUMPS, 6 threads) | 178.6 |
| `total` | 483.9 |

Problem size, from `logs/modal.log`: 126 547 cells, 197 638 nodes, **592 914
DOFs** at P2, clamped hub (77 facets, 573 fixed DOFs). SLEPc converged 11 of 10
requested eigenpairs.

### 1.2 Combined chain — `tistos-combined-dev`

One candidate at the time of writing. This is the run that first split the CFD
stage in two (`cfd_build` / `cfd_solve`, added for exactly this question).

| Stage | Seconds | Scales with |
|---|---|---|
| `cfd_build` (dtOO case build) | 224.1 | nothing — single-threaded gmsh |
| `cfd_solve` (simpleFoam) | 134.5 | `mpi_ranks` |
| `mesh` (dtOO export) | 371.0 | nothing — single-threaded gmsh |
| `modal` (SLEPc/MUMPS, 1 thread) | 265.1 | `threads_per_rank` |
| `total` | 995.3 | |

CFD mesh: ~60 000 cells (stated by the user; not derivable from the collected
logs, because the solve script redirects OpenFOAM output into `log.<name>` files
inside the case directory rather than into `cfd_solve.log`).

### 1.3 Two consistency checks that passed

**The objective composes as documented.** `f_cfd` 1.808 95 + `f_resonance`
4.921 86 = 6.730 81, against a reported objective of 6.730 82.

**The configs differ only in `eval_mode`.** Candidate `island-000-initial-000`
returned `f_1 = 21.5219` Hz in the freq-only run and the identical value in the
combined run. `cluster/configs/README.md` requires the three runs to be
comparable candidate by candidate; this is the first evidence for it rather than
an assertion.

---

## 2. The decision: fewer ranks, more concurrent candidates

### The question

OpenFOAM parallelises well and scales close to linearly on large meshes, which
argues for spending the core budget on `mpi_ranks`. The measurement says the
opposite for this workload.

### Why more ranks cannot help much

**Amdahl.** Only `cfd_solve` responds to `mpi_ranks`: 134.5 s of a 995.3 s
combined candidate, or 13.5%. Driving simpleFoam to zero with unlimited ranks
would make a candidate 13.5% faster. Everything else — the dtOO case build, the
dtOO mesh export — is single-threaded and indifferent.

**Throughput, not latency.** A DE generation completes when all its candidates
do, so what matters is evaluations per second, not the latency of one. For a
fixed core budget:

```
throughput = concurrency / T(ranks),   concurrency = cores / ranks
```

Under *perfect* linear scaling `T(ranks) = T₁/ranks`, and both cancel:
throughput is independent of the split. Perfect scaling is the case where the
choice stops mattering — not the case where many ranks win. Every real
sub-linearity then favours fewer ranks and more concurrent candidates.

**Cells per rank.** ~60k cells at the previous 6 ranks is 10k cells/rank,
already the lower edge of where OpenFOAM scales (rule of thumb: 20–50k). Twelve
ranks would give 5k, thirty-two would give under 2k, where communication
dominates and adding ranks makes the solve slower.

### The arithmetic

Serial part `S = 995.3 − 134.5 = 860.8 s`, assuming `cfd_solve` scales
inverse-linearly from its 6-rank measurement. 64 cores, `threads_per_rank = 1`:

| Ranks | Cells/rank | Candidate | Concurrent | Cores used | Throughput |
|---|---|---|---|---|---|
| 12 | 5 000 | 928 s | 5 | 60 | 0.54× |
| 6 (was) | 10 000 | 995 s | 10 | 60 | 1.00× |
| **4 (now)** | **15 000** | **1 063 s** | **16** | **64** | **1.50×** |
| 3 | 20 000 | 1 130 s | 16 (memory-capped) | 48 | 1.42× |

The 4-rank estimate is conservative: at 15k rather than 10k cells/rank the solve
is *more* efficient per rank than inverse-linear scaling assumes.

### What changed

`cluster/configs/tistos-cfd-only.toml` and `cluster/configs/tistos-combined.toml`:

```toml
concurrent_evaluations = 16   # was 10
mpi_ranks              = 4    # was 6
```

Both files, identically and in the same commit. `mpi_ranks` decides the
`decomposePar` partitioning and therefore the CFD numbers; the two runs are only
comparable while it matches. `cluster/submit_hydroflow_opt.sh` deliberately
scales only `concurrent_evaluations` and `threads_per_rank` to an allocation and
never `mpi_ranks`, so the same config yields the same CFD results on any
partition.

`tistos-freq-only.toml` is untouched: `resonance_only` runs no CFD, so
`mpi_ranks` is meaningless there.

### Rejected alternatives

**More ranks per candidate.** 13.5% of the work responds; the mesh is too small
to divide further. Rejected on both counts.

**More threads for the modal solve.** Measured 265 s at 1 thread against 179 s
at 6 — 1.48× for six times the cores. Concurrency uses those cores far better.

**Concurrency above 16.** Memory becomes the constraint before cores do: 16
concurrent modal solves at ~11 GB is 176 GB of 251 GiB. 21 × 3 would want
231 GB, which leaves no headroom for an estimate that has never been measured.

---

## 3. What the production runs will cost

Per candidate at 4 ranks, scaling `cfd_solve` inverse-linearly from its 6-rank
measurement (224.1 + 134.5 × 6/4 = 425.9 s of CFD):

| Run | Evaluations | s/candidate | At concurrency 16 | 48 h windows |
|---|---|---|---|---|
| `tistos-cfd-only` | 6 000 | 426 | 44 h | 1 |
| `tistos-freq-only` | 3 120 | 484 | 26 h | 1 |
| `tistos-combined` | 6 000 | 1 062 | 111 h | 3 |

`combined` cannot finish in one window and is not meant to — the config says so
("sized to outlast the 48 h walltime"). It needs roughly three submissions, each
resuming from the last checkpoint. `cfd-only` fits one window with about 8%
headroom, which is thin enough that a resubmission should be expected rather
than treated as a failure.

Both are submitted at 24 generations so they compare at equal search depth. If
`combined` is stopped early for time, the comparison must be truncated to the
generation it actually reached — `optimization/history.jsonl` in the run
directory records per-generation progress.

## 4. Partition choice

| Partition | Cores | Memory | Note |
|---|---|---|---|
| `cpu_il` | 64 | 256 GiB | more nodes, shorter queue |
| `cpu` | 96 | 384 GiB | fewer nodes, longer queue |

`cpu_il` is the recommendation. The extra 32 cores of `cpu` would go into
`threads_per_rank`, which the measurement above shows to be the weakest of the
three levers, while the queue wait is reported to be materially longer.

Nothing has to change to move between them: submitting a 96-core config to a
64-core allocation makes `submit_hydroflow_opt.sh` scale `threads_per_rank`
down, log a `scaling to the allocation` line, and leave results unaffected.

---

## 5. What is still an estimate

Marked explicitly, because everything above reads like measurement and only some
of it is.

| Quantity | Status |
|---|---|
| Per-stage seconds, combined | **One candidate.** `mesh` varied 304 s → 371 s between the two runs, so treat ±20% as normal. |
| 13.5% parallel fraction | Follows from that single candidate. The margin to the alternatives is large enough that the direction holds, the exact figure is not load-bearing. |
| ~11 GB per modal solve | **Never measured on tistos.** Carried over from a different case at 545 247 DOFs; this mesh has 592 914, so the real figure is likely higher. This is the number that caps concurrency. |
| `cfd_solve` scaling from 6 ranks | Assumed inverse-linear. Conservative for fewer ranks, optimistic for more. |
| ~60k CFD cells | Stated by the user, not read from a log. |

The memory figure is the one worth closing first: `sacct -j <jobid> -o MaxRSS`
after the first production run turns it into a measurement, and if it lands
materially above 11 GB, `concurrent_evaluations` has to come back down.

---

## 6. Why this measurement did not exist earlier

Three defects in the dtOO export path, each of which made every
`resonance_only` and `combined` candidate fail while `cfd_only` kept working.
All three are fixed on this branch.

| Defect | Cause | Why cfd_only never showed it |
|---|---|---|
| `can't open file .../physics.py` | argv used `Path(__file__).resolve()` while the mount kept the unresolved name; `$HOME` is a symlink on bwUniCluster | The CFD build composes its script path from `_repo_root()` and never calls `run_dtoo_export` |
| `Failed to open fileName = machineSave.xml` | dtOO chdirs into the case directory and opens it `ReadWrite`; the configured directory is inside the image and enroot mounts the rootfs read-only | The CFD stage stages the case per candidate and writes into the candidate's own directory |
| No 30-minute config exercised the modal stage in `optimize` mode | `tistos-smoke.toml` is `run` mode with fixed candidates and predates the shared enroot cache | — |

The pattern is worth keeping in mind: a green `cfd_only` run says nothing about
the freq half, because the two use different code paths for the same geometry
step.

---

## 7. Open questions

- **Does the resonance penalty ever reach zero?** All five freq-only candidates
  scored above zero, so every design so far has a mode inside a forbidden band.
  Whether the DE can find a design that leaves the band is the question the
  production runs exist to answer.
- **Is `f_1` the mode that matters?** It landed at 21.52 Hz against a
  blade-passing frequency of 21.6 Hz — essentially resonant for the baseline
  design. Across five candidates `f_1` ranged 19.0–36.2 Hz, so the design vector
  moves it substantially.
- **Memory per modal solve**, as above.
