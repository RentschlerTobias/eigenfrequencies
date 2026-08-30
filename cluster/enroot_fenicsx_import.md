# FEniCSx enroot import guide — bwUniCluster 3.0

How to get the modal solver onto bwUniCluster, and how to set up the venv that
drives the optimization. The counterpart to `enroot_dtoo_import.md`; both
containers are needed for a `combined` run, only the dtOO one for `cfd_only`.

> **User-dependent steps** are marked with `[USER]`.

## Nothing has to be copied

Both images live on Docker Hub, and enroot imports from a registry directly. No
`scp`, no registry account, no 3.9 GB through your laptop:

```bash
mkdir -p ~/enroot-images && cd ~/enroot-images
enroot import -o dtOO-opensuse.sqsh docker://atismer/dtoo-opensuse:stable
enroot import -o dolfinx.sqsh       docker://dolfinx/dolfinx:stable
```

Git is the wrong tool for this and always was: these are multi-GB binary layers
that would sit in the history forever, which is why `enroot-images/` is in
`.gitignore`.

## The one thing the stock image is missing

`dolfinx/dolfinx:stable` has no `gmsh` Python module, and without it the modal
stage cannot read a `.msh` at all. That does **not** justify building a custom
image: gmsh is a self-contained wheel, and 17 MB on the shared filesystem does
the job.

```bash
# [USER] on a login node, which has internet
python3 -m pip install --target ~/pylibs gmsh
```

The configs point at it:

```toml
[case.options.modal]
container = "~/enroot-images/dolfinx.sqsh"
pythonpath = ["~/pylibs"]
```

`pythonpath` is mounted into the container automatically and **appended** to the
existing `PYTHONPATH` — never assigned. The dolfinx image keeps its own dolfinx
on that variable (`/usr/local/dolfinx-real/lib/python3.12/dist-packages`), so
overwriting it produces `ModuleNotFoundError: No module named 'dolfinx'` inside
an image that plainly has dolfinx. That mistake is one line and costs an
allocation to discover.

Verified: stock image + mounted gmsh returns the same five frequencies as the
custom-built image, digit for digit.

## If you would rather have one self-contained image

`docker/fenicsx.Dockerfile` builds dolfinx + gmsh + scipy + the package, and
`cluster/export_fenicsx_enroot.sh` writes a 1.6 GB `tar.gz` for transfer. It
works and is tested, but it needs a machine with Docker, a way to move 1.6 GB to
the cluster, and it embeds a copy of the repository in the image. Prefer the
route above unless you need the package installed inside the container.

```bash
bash cluster/export_fenicsx_enroot.sh ./enroot-images
scp ./enroot-images/eigenfrequencies-fenicsx.tar.gz <cluster>:~/enroot-images/
enroot import -o fenicsx.sqsh docker-archive://eigenfrequencies-fenicsx.tar.gz
```

## Smoke test `[USER]`

```bash
sbatch cluster/submit_fenicsx_enroot_smoke.sh
tail -f fenicsx_enroot_smoke_*.out
```

This one solves rather than only importing: the modal stage on the coarse
unit-box fixture, a few hundred DOFs and seconds of work. A green run ends with
a `RESULT_JSON` line carrying five frequencies. If that works, gmsh, dolfinx,
the eigensolver and the mount layout are all correct.

Set `ENROOT_IMAGE=~/enroot-images/dolfinx.sqsh` and `PYLIBS=~/pylibs` if you
took the stock-image route.

## Troubleshooting

### `ModuleNotFoundError: No module named 'gmsh'`

`pythonpath` is missing from the config, or `~/pylibs` was never populated.

### `ModuleNotFoundError: No module named 'dolfinx'` in the dolfinx image

`PYTHONPATH` was assigned instead of appended. See above.

### `RuntimeError: Multiple index maps of this dimension`

The mesh mixes cell types — hexahedra with prisms, for instance. dolfinx 0.11
cannot build a function space on it. This is what makes the naca case unusable
for modal analysis; see the header of `adapters/machines/naca.yaml`.

### PMIx errors about `/run/user/<uid>`

`HOME`, `TMPDIR` and `XDG_RUNTIME_DIR` were not redirected to `/tmp`. The
physics stage does this itself; if you start the container by hand, do the same.

### The job runs out of memory

The modal solve needs ~10 GB per candidate — MUMPS' own figure for the tistos
matrix at P2, measured. Lower `concurrent_evaluations`, and
`optimization.islands` with it.

## The driving venv `[USER]`

hydroflow-opt runs *outside* both containers, on the node, and needs
`eigenfrequencies` installed alongside it — otherwise the `hydroflow_opt.cases`
entry point cannot resolve `tistos`:

```bash
python3 -m venv ~/venvs/hydroflow
~/venvs/hydroflow/bin/pip install hydroflow-opt
~/venvs/hydroflow/bin/pip install -e /path/to/eigenfrequencies[hydroflow]
```

Verify before submitting anything:

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

## Order of work `[USER]`

The production partitions queue a 24–48 h job for 5–7 days, so there is
realistically one attempt. Everything below runs in the 30-minute `dev_cpu_il`
window first.

```bash
DRY_RUN=1 bash cluster/submit_hydroflow_opt.sh cluster/configs/tistos-smoke.toml
sbatch cluster/submit_dtoo_enroot_smoke.sh
sbatch cluster/submit_fenicsx_enroot_smoke.sh
sbatch --partition=dev_cpu_il --time=00:30:00 \
       cluster/submit_hydroflow_opt.sh cluster/configs/tistos-smoke.toml
```

The last one puts two real candidates through the whole chain and, more
importantly, reports how long one evaluation actually takes — which is what the
production walltime has to be based on.
