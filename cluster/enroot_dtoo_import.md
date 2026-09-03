# dtOO enroot import guide — bwUniCluster 3.0

This document describes how to get the `atismer/dtoo-opensuse:stable` Docker
image onto bwUniCluster 3.0 as an enroot squashfs image and verify that the
dtOO SWIG bindings load inside a SLURM job.

> **User-dependent steps** are marked with `[USER]`. They must be executed on
> a host with network access to the cluster (login node or your local machine
> with a working SSH key).

---

## 1. Export the Docker image locally

On the machine that has the Docker daemon and the image cached:

```bash
cd /root/repos/duty/eigenfrequencies
bash cluster/export_dtoo_enroot.sh ./enroot-images
```

This produces:

```
./enroot-images/atismer_dtoo-opensuse_stable.tar.gz
```

The script also prints the image ID and size. Keep the output for the evidence
log.

---

## 2. Transfer the tarball to the cluster `[USER]`

The target is the **workspace**, not `$HOME`: that is where the jobs look
(`cluster_env.sh:56`, `submit_hydroflow_opt.sh` staging block). Print the path
on a login node first, then substitute it for `<WS>` below:

```bash
source ~/eigenfrequencies/cluster/cluster_env.sh && echo "$WS/enroot-images"
```

Replace `st_ac136362` with your bwUniCluster account:

```bash
scp ./enroot-images/atismer_dtoo-opensuse_stable.tar.gz \
    st_ac136362@bwunicluster.scc.kit.edu:"<WS>/enroot-images/"
```

`cluster_env.sh` creates that directory when it is sourced, so it exists after
the command above.

---

## 3. Import the image into enroot `[USER]`

Log in to a bwUniCluster login node and run:

```bash
source ~/eigenfrequencies/cluster/cluster_env.sh
cd "$ENROOT_IMAGES"
enroot import -o "$ENROOT_IMAGES/dtOO.sqsh" docker-archive://atismer_dtoo-opensuse_stable.tar.gz
```

**Source `cluster_env.sh` first, always.** It sets
`ENROOT_SQUASH_OPTIONS="-comp zstd -noD"` — without it `mksquashfs` defaults to
lzo, and an lzo image imports fine but is unreadable on every compute node. It
also sets `ENROOT_IMAGES=$WS/enroot-images`, which is the one directory the jobs
look in.

The file name matters as much as the location: the submit script derives the
container name from the basename (`dtOO.sqsh` → `dtOO`) and the configs ask for
`container = "dtOO"`. A `dtOO-opensuse.sqsh` yields a container called
`dtOO-opensuse` that nothing ever starts.

Expected output: a `.sqsh` file is created with no error.

Alternative if the direct `docker-archive://` URI is not supported by the
cluster's enroot version:

```bash
# Uncompress first, then import the plain tar.
gunzip -c atismer_dtoo-opensuse_stable.tar.gz > atismer_dtoo-opensuse_stable.tar
enroot import -o "$ENROOT_IMAGES/dtOO.sqsh" docker-archive://atismer_dtoo-opensuse_stable.tar
```

---

## 4. Run the enroot smoke test `[USER]`

From the repository checkout on the cluster:

```bash
cd /home/st/st_us-042020/st_ac136362/eigen/eigenfrequencies
sbatch cluster/submit_dtoo_enroot_smoke.sh
```

The job requests one node, one task, and five minutes on `dev_cpu_il`. It
starts the container, sources the OpenFOAM and dtOO environment files, and
runs:

```bash
python3.13 -c "import dtOOPythonSWIG; print('dtOOPythonSWIG imported ok')"
```

Check the output:

```bash
tail -f dtOO_enroot_smoke_*.out
```

A successful run prints `dtOOPythonSWIG imported ok` and exits with code 0.
The Gmsh warnings (`Warning : Gmsh has aleady been initialized`) are harmless.

---

## 5. Troubleshooting

### `ImportError: libPstream.so`

The OpenFOAM bashrc was not sourced. The smoke-test script already sources
`/usr/lib/openfoam/openfoam2606/etc/bashrc`; if you run the container
manually, do the same before `python3.13`.

### `ImportError: libTKFeat.so.7.9`

The dtOO environment was not sourced. Source `/dtOO-install/bin/env.sh` before
running Python.

### enroot cannot find `docker-archive://`

Use the uncompressed tar fallback shown in section 3, or ask cluster support
which import URI scheme is supported.

### Container starts but `python3.13` is missing

The current image (`sha256:25ef00d004de`) provides `python3.13`. If a future
image changes the Python version, update `submit_dtoo_enroot_smoke.sh`
accordingly.

---

## 6. Use in production jobs

After the smoke test passes, reference the squashfs image in your sbatch
scripts with:

```bash
srun -n1 -N1 enroot start --root \
    --mount "$CASE_DIR:/case:ro" \
    --mount "$WORK_DIR:/work:rw" \
    "$WS/enroot-images/dtOO.sqsh" \
    bash -c 'source /usr/lib/openfoam/openfoam2606/etc/bashrc && \
             source /dtOO-install/bin/env.sh && \
             python3.13 /work/run_dtoo_task.py'
```

See `cluster/env_notes.md` for the full integration pattern with Pyro5 workers.
