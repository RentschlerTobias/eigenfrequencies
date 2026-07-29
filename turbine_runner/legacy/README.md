# Legacy Optimizers

Archived copies of the original host-side optimization drivers.

These files are kept for **de_state / de_history compatibility** — the JSON
checkpoint and history files they produced are referenced by characterization
tests and golden references.  The code itself is **superseded** by the
`eigenfrequencies.optimize` package and is no longer the recommended entry
point for new runs.

| File | Status |
|------|--------|
| `optimize.py` | Original scipy.optimize.minimize driver (resonance-only). Superseded by `eigenfrequencies.optimize.backends.scipy`. |
| `optimize_multi.py` | Multi-objective driver (CFD + resonance). Superseded by `eigenfrequencies.optimize.backends.combined`. |

Both files still import from the `eigenfrequencies` package where possible,
but they retain legacy field names (`f_min` / `f_max`) and container-call
patterns that differ from the current package API.
