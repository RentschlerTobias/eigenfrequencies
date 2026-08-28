# Eigensolver Backends

The modal solver ships two eigensolvers. They solve the same generalized
eigenproblem and, on the same input, return the same frequencies to machine
precision. Choosing between them is a question of how the linear algebra is
carried out, not of what is being computed.

```
K x = λ M x        K stiffness, M mass, λ = (2πf)²
```

| | `scipy` | `slepc` |
|---|---|---|
| Library | `scipy.sparse.linalg.eigsh` (ARPACK) | PETSc + SLEPc, Krylov–Schur |
| Constrained DOFs | sliced out of the CSR matrices | unit/zero diagonal, matrix stays whole |
| Factorization | on the restricted system | MUMPS, distributed |
| Scales to | ~10⁵–10⁶ DOFs | past ~10⁶ DOFs |
| Needs | scipy | `petsc4py`, `slepc4py`, MUMPS |

Select one with `SolverConfig.solver_backend`, or from a hydroflow-opt config:

```toml
[case.options.modal.solver]
element_degree = 2
solver_backend = "slepc"    # or "scipy"
```

Both accept every `BCConfig.mode`: `radius_band` (the runner hub clamp),
`axial_plane` (a foil or disc root) and `free` (free-free suspension).

## How each one imposes a clamp

This is the only real difference between them, and it is worth understanding
before picking one for a large problem.

**scipy removes the constrained degrees of freedom.** The Dirichlet DOFs are
dropped from K and M and the reduced system is handed to ARPACK. The result is
a smaller problem with no artificial modes in it — clean, and the natural thing
to do when the matrices are small enough to slice.

**SLEPc keeps them and makes them harmless.** The constrained rows are
assembled with a unit diagonal in K and a **zero** diagonal in M, so their
eigenvalue is 1/0 — infinite. The solver runs shift-invert around
`sigma = -1`, which maps λ to `θ = 1/(λ - σ)`; an infinite λ therefore becomes
`θ = 0`, the smallest transformed magnitude, at the opposite end of the
spectrum from the modes being searched for. The spurious rows are still in the
matrix, but they can never compete with the physical modes.

Why bother instead of slicing? Because slicing rebuilds the sparsity pattern,
and the sparsity is the entire reason to reach for SLEPc. Keeping the matrix
whole is what lets MUMPS factor it in distributed memory.

As a safety net the backend drops any eigenvalue that is not finite or exceeds
`1e30`, in case PETSc reports a very large number instead of an exact infinity.

## They agree

On the coarse unit-box fixture, P2 elements, clamped at `z = 0`:

```
scipy  2819.2647  2953.6796  2995.8114  3520.2568  3726.8807  Hz
slepc  2819.2647  2953.6796  2995.8114  3520.2568  3726.8807  Hz

maximum relative deviation: 6.07e-14 %
```

`tests/solver/test_backend_equivalence.py` pins this, together with two
properties that would break silently otherwise: a clamped spectrum contains no
rigid-body modes and no surviving spurious mode, and the free-free spectrum
still contains its rigid-body modes. If the two backends ever drift apart, one
of them is wrong and the choice is no longer free — which is exactly when a
config knob becomes dangerous.

## Which to use

Use **scipy** for local work, validation cases and anything comfortably below
a few hundred thousand DOFs. It has fewer moving parts and no MUMPS dependency.

Use **slepc** when the factorization is what limits you. The tistos runner at
P2 is roughly 545 000 DOFs, which is where the choice starts to matter; the
cluster configs in `cluster/configs/` default to it for that reason.

If MUMPS turns out to be the memory problem rather than the solution, switching
back is one line and the frequencies do not change.

## History

Until 2026-08-28 the SLEPc path rejected anything but `mode="free"`: it had
been written for the free-hanging validation disc, and `solver/core.py` raised
`SolverConfigError` for a clamped configuration. That made "P2 + SLEPc" — the
combination the tistos runs were planned around — impossible without also
un-clamping the runner, which would have changed the physics rather than the
numerics. The assembly-based clamp described above removed the restriction.

## Related

* `docs/cluster.md` — running the modal solve inside the FEniCSx container
* `cluster/configs/README.md` — the three comparison runs and their settings
* `src/eigenfrequencies/solver/slepc_backend.py` — the shift-invert setup
* `src/eigenfrequencies/solver/scipy_backend.py` — the DOF restriction
