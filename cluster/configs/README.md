# The three comparison runs

One config per run. They differ in **exactly one line** — `eval_mode` — because
the point of the comparison is what the resonance term does to the optimum, not
what a different search does:

| Config | `eval_mode` | Physics per candidate |
|---|---|---|
| `tistos-cfd-only.toml` | `cfd_only` | dtOO + simpleFoam |
| `tistos-freq-only.toml` | `resonance_only` | dtOO + modal solve |
| `tistos-combined.toml` | `combined` | both |

Population, generations, islands, differential weight, crossover rate and seed
are identical in all three, so the DE visits the same initial population and
the runs are comparable candidate by candidate.

**Run `cfd_only` first.** It is the cheapest — no modal solve — and it is the
one that proves the CFD objective actually varies. If `f_cfd` freezes again,
that shows up after hours instead of after days. The sanity gate is the
`unique` count per metric over all generations; a frozen metric has a count
of 1. That check is what exposed runs 6039132/6039133.

## Before submitting

The two blocks marked `[USER]` in each file:

1. **`[resources]`** — sized for a 40-core / 96 GB node. `submit_hydroflow_opt.sh`
   refuses to start if the allocation is smaller, so a wrong guess costs
   seconds, not a run. The binding constraint is memory, not cores: at ~28.6 GB
   peak per modal solve only three evaluations fit on 96 GB, which is why 28 of
   40 cores sit idle in the modal runs. Raise `mpi_ranks` to spend them on
   simpleFoam.
2. **`[run] directory`** — a workspace path, not `$HOME`. The scratch directory
   is redirected to node-local `$TMPDIR` by the submit script.

Two invariants hydroflow-opt enforces when it loads the config, both before the
first evaluation:

```
concurrent_evaluations × mpi_ranks × threads_per_rank ≤ available_cpus
optimization.islands                                  ≤ concurrent_evaluations
```

## Eigensolver: a config switch, not a fork in the physics

The plan called for "P2 + SLEPc", and SLEPc used to reject anything but a
free-free boundary condition — while tistos clamps its hub. That restriction is
gone: the clamp is now imposed by assembly (unit diagonal in K, zero in M, so
the constrained rows sit at an infinite eigenvalue) instead of by removing DOFs,
which is what keeps the matrices sparse.

Both backends therefore solve the same clamped problem, and they agree to
machine precision — 6e-14 % on the fixture mesh, pinned by
`tests/solver/test_backend_equivalence.py`. Switching is one line:

```toml
[case.options.modal.solver]
solver_backend = "slepc"    # or "scipy"
```

| | `slepc` (default here) | `scipy` |
|---|---|---|
| Constrained DOFs | unit/zero diagonal, matrix stays sparse | sliced out of the CSR matrices |
| Factorization | MUMPS, distributed | ARPACK on the restricted system |
| Scales to | past ~10^6 DOFs | ~10^5–10^6 |

tistos at P2 is roughly 545k DOFs, which is exactly the range where the choice
starts to matter — hence SLEPc as the default. If MUMPS turns out to be the
memory problem rather than the solution, switch to scipy; the frequencies do
not change.

Free-free (`modal.bc.mode = "free"`) remains available for validation against
an unmounted disc, but it is not the machine: the runner is bolted to a shaft.

The ~28.6 GB in `[resources]` is still an estimate carried over from the
validation case, not a measurement of tistos with either backend. The first run
turns it into a number.
