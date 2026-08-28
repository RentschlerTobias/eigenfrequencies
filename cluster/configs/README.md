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

## Open decision: SLEPc vs. the hub clamp

The plan calls for "P2 + SLEPc" in all three runs. **That combination does not
exist in the code.** `solver/core.py:146-150` rejects `solver_backend="slepc"`
unless `bc.mode == "free"`, and tistos' machine YAML clamps the hub
(`bc_template: hub_clamp` → `radius_band`). The SLEPc path is a free-free
shift-invert; it was written for the validation disc, which hangs free.

These configs therefore use **P2 + scipy with the hub clamp** — the
discretization from Q6, the boundary condition from the machine. Three ways
out, in order of what they cost:

* keep scipy (this default): correct BC, but the factorization is the memory
  wall — that is where the ~28.6 GB comes from;
* switch to free-free + SLEPc (`modal.bc.mode = "free"`,
  `modal.solver.solver_backend = "slepc"`): scales past 10^6 DOFs, discards the
  first 6 rigid-body modes — but the runner then vibrates unattached, which is
  not the machine;
* teach the SLEPc backend the clamped case: right answer, real work, not a
  config change.

The first run will show whether scipy fits in memory at all. Until then the
number in `[resources]` is an estimate carried over from the validation case,
not a measurement of tistos.
