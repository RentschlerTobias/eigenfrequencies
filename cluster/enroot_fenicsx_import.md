# FEniCSx enroot import guide — bwUniCluster 3.0

How to get the modal solver onto bwUniCluster 3.0 as an enroot image, and how
to set up the venv that drives the optimization. The counterpart to
`enroot_dtoo_import.md`; both containers are needed for a `combined` run,
only the dtOO one for `cfd_only`.

> **User-dependent steps** are marked with `[USER]`. They need cluster access.

Unlike dtOO this image is **built, not pulled**. `dolfinx/dolfinx:stable` has
no `gmsh` Python module, and without it `eigenfrequencies.io.load` cannot read
a `.msh` at all — the modal stage would fail on its first candidate.
`docker/fenicsx.Dockerfile` adds gmsh, scipy and the package.

---

## 1. Build and export the image locally

```bash
cd /root/repos/duty/eigenfrequencies
bash cluster/export_fenicsx_enroot.sh ./enroot-images
```

The script builds if needed, verifies that `dolfinx` and `gmsh` import, then
saves and compresses. Result:

```
./enroot-images/eigenfrequencies-fenicsx.tar.gz
```

It builds with `--network=host`. On a host where IPv4 forwarding is disabled
the default bridge cannot resolve DNS, and since image *pulls* go through the
daemon, that only surfaces at the first `pip install` inside the build.

---

## 2. Transfer to the cluster `[USER]`

```bash
scp ./enroot-images/eigenfrequencies-fenicsx.tar.gz \
    st_ac136362@bwunicluster.scc.kit.edu:~/enroot-images/
```

---

## 3. Import `[USER]`

```bash
cd ~/enroot-images
enroot import -o fenicsx.sqsh docker-archive://eigenfrequencies-fenicsx.tar.gz
```

If the `docker-archive://` URI is not supported, uncompress first — same
fallback as for dtOO:

```bash
gunzip -c eigenfrequencies-fenicsx.tar.gz > eigenfrequencies-fenicsx.tar
enroot import -o fenicsx.sqsh docker-archive://eigenfrequencies-fenicsx.tar
```

The configs in `cluster/configs/` expect the result at
`~/enroot-images/fenicsx.sqsh`; adjust `case.options.modal.container` if you
put it elsewhere.

---

## 4. Smoke test `[USER]`

```bash
sbatch cluster/submit_fenicsx_enroot_smoke.sh
tail -f fenicsx_enroot_smoke_*.out
```

This one solves rather than only importing: it runs the modal stage on the
coarse unit-box fixture, a few hundred DOFs and seconds of work. A green run
ends with a `RESULT_JSON` line carrying five frequencies. If that works, gmsh,
dolfinx, the eigensolver and the mount layout are all correct.

---

## 5. Troubleshooting

### `ModuleNotFoundError: gmsh`

The image was built from plain `dolfinx/dolfinx:stable` instead of
`docker/fenicsx.Dockerfile`. Rebuild.

### `RuntimeError: Multiple index maps of this dimension`

The mesh mixes cell types — hexahedra with prisms, for instance. dolfinx 0.11
cannot build a function space on it. This is what makes the naca case
unusable for modal analysis; see the header of `adapters/machines/naca.yaml`.

### PMIx errors about `/run/user/<uid>`

`HOME`, `TMPDIR` and `XDG_RUNTIME_DIR` were not redirected to `/tmp`. The smoke
script and `physics.py` both do this; if you start the container by hand, do
the same.

### The job runs out of memory

The modal solve peaks around 28.6 GB per candidate (an estimate carried over
from the validation case, not yet measured on tistos). Lower
`concurrent_evaluations` — and `optimization.islands` with it, since islands
must not exceed it.

---

## 6. The driving venv `[USER]`

hydroflow-opt runs *outside* both containers, on the node. It needs its own
venv — and `eigenfrequencies` must be installed in it too, otherwise the
`hydroflow_opt.cases` entry point cannot resolve `tistos`:

```bash
python3 -m venv ~/venvs/hydroflow
~/venvs/hydroflow/bin/pip install hydroflow-opt
~/venvs/hydroflow/bin/pip install -e /path/to/eigenfrequencies[hydroflow]
```

Verify the case is discoverable before submitting anything:

```bash
~/venvs/hydroflow/bin/python -c \
  "from hydroflow_opt.cases import case_from_name; \
   print(len(case_from_name('tistos').parameter_space({}).names), 'parameters')"
```

Expected: `30 parameters`. If it raises, set
`EIGENFREQUENCIES_MACHINES_DIR=<repo>/adapters/machines` — the catalog lives
outside `src/` and does not travel with a non-editable install.

`submit_hydroflow_opt.sh` looks for the venv at `~/venvs/hydroflow`; override
with `HYDROFLOW_VENV`.

---

## 7. Running the three optimizations `[USER]`

```bash
sbatch cluster/submit_hydroflow_opt.sh cluster/configs/tistos-cfd-only.toml
# then, after the gate passes:
sbatch cluster/submit_hydroflow_opt.sh cluster/configs/tistos-freq-only.toml
sbatch cluster/submit_hydroflow_opt.sh cluster/configs/tistos-combined.toml
```

The order is not arbitrary — see `cluster/configs/README.md`. After each run:

```bash
python3 cluster/summarize_run.py runs/tistos-cfd-only
```

Exit code 0 means every metric varied and nothing failed. A metric reported as
`FROZEN` means the run produced one value for it across every candidate; that
is not convergence, it is the failure that invalidated runs 6039132/6039133.
