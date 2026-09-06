# Why no candidate ever finished on bwUniCluster

**Investigation log, 2026-09-04 to 2026-09-06.** Branch `fix/bwuni-enroot-hardening`.

Written so a different session can check the work rather than repeat it. Every
claim carries the command that produced it; where something is inference rather
than measurement, it says so. Section 6 lists the hypotheses that turned out to
be wrong — likely the part that saves the most time.

**Status:** five causes found and fixed; the CFD solve still fails. The geometry
export, which had never once completed, now runs in 144 s and produces a mesh
matching the local reference.

**Companion:** `docs/cluster-dtoo-enroot-befund-v2.md` §4 P0-3 records the
symptom in the wider context of the cluster work.

---

## 1. The symptom, and how to reproduce it

A `cfd_only` evaluation produced **nothing**: no artifact, no log line, no error.
It sat until its 1800 s timeout and was recorded as a failure with an empty log.

Per the repository owner, **no case had ever completed with this setup** — this
was never a regression. The reference implementation (`de_framework`) puts the
same tistos case (3-D, 30 parameters) through mesh *and* solve for several
individuals inside a 30-minute `dev_cpu_il` window, so "it is simply a heavy
case" was never credible.

To reproduce, on a compute node with at least 12 cores:

```bash
cd ~/eigenfrequencies && git pull
source cluster/interactive_setup.sh
bash cluster/rerun_smoke.sh
```

Current outcome: `run complete: 0/2 succeeded`, build logs of ~3400 lines each,
solve logs of 2 lines (just the command header), and in the OpenFOAM case
directory:

```
tistos_ru_of_n_hydroflow/log.checkMesh:
  checkMesh: error while loading shared libraries: libfiniteVolume.so:
  cannot open shared object file: No such file or directory
```

---

## 2. Tooling added during the investigation

All of it lives in `cluster/` and is meant to be re-run.

| script | answers |
|---|---|
| `interactive_setup.sh` | Per-allocation setup: `WS`, `R`, `W`, `ENROOT_DATA_PATH`, unpacks the containers. Source it in **every** shell on the node — a second window from `srun --overlap` starts empty, and a lost `$W` silently turns `-m "$W:$W"` into `-m ":"`. |
| `rerun_smoke.sh` | Archives the previous run (results, scratch **and** the local stage logs), submits, then prints the first line of every stage log — which is the exact command that ran. |
| `probe_openfoam_cd_order.sh` | Does `cd` before sourcing OpenFOAM loop the container shell? (R1) |
| `probe_container_env.sh` | What do `PATH` and `LD_LIBRARY_PATH` look like after each setup step? |
| `probe_solve_env.sh` | Six combinations of `--rc` × setup lines, each running `checkMesh`. |
| `probe_solve_shell.sh` | Nine-row bisect: adds mounts, `--rc`, `cd`, exports and the setup lines one at a time to the bare call that works. |
| `enroot_rc.sh` | The replacement container command script (`exec "$@"`), see R5. |
| `configs/tistos-smoke-cfd.toml` | 2-candidate `cfd_only` smoke, solve in the container. |
| `configs/tistos-smoke-cfd-native.toml` | Same, but the solve runs from the cluster's OpenFOAM module. |

---

## 3. Measured facts about the container

Each is a single command; none needs the pipeline.

**The image supplies a complete OpenFOAM environment.**

```bash
enroot start --root dtOO checkMesh -help          # works, "Using: OpenFOAM-2606"
enroot start --root dtOO bash -c 'echo $LD_LIBRARY_PATH'
```

The path already contains
`/usr/lib/openfoam/openfoam2606/platforms/linux64GccDPInt32Opt/lib`, and `bash -c`
and `bash -lc` produce byte-identical output.

**dtOO's Python bindings need their own environment.**

```bash
enroot start --root dtOO python3.13 -c 'import dtOOPythonSWIG'
# ImportError: libTKFeat.so.7.9
```

`/dtOO-install/bin/env.sh` only ever prepends (lines 102, 113), so it cannot
remove anything.

**`mpiexec` does not exist in the image; `mpirun` does.** All four OpenFOAM
utilities the solve script calls are present.

```bash
enroot start --root dtOO bash -c 'command -v mpirun mpiexec simpleFoam checkMesh decomposePar reconstructPar'
```

**`/bin/sh` in the image is a symlink to `bash`** — the solve does not run under
a different shell.

**Unpacking is cheap:** 8.2 s cold, 3.8 s warm, for the 5.8 GB image onto
node-local scratch (`time enroot create`).

**Both images are correctly named** in `$WS/enroot-images`: `dtOO.sqsh` (5.8 GB),
`dolfinx.sqsh` (2.78 GB), imported 2026-08-30.

---

## 4. Causes found and fixed

### R1 — `cd` before sourcing loops the container shell (`519ebf1`)

`Runtime.command` built every container command as
`bash -c "cd <workdir>; source .../etc/bashrc; source .../env.sh; exec <payload>"`.
Changing directory *before* sourcing OpenFOAM's bashrc makes the shell reprint
everything ahead of the source several times a second and never return. The
trailing `exec` never helps, because control never reaches it.

`bash cluster/probe_openfoam_cd_order.sh`:

| variant | payload | result |
|---|---|---|
| A | `cd /tmp; date; source bashrc; echo REACHED` | 109 lines in 20 s, `REACHED` never printed |
| B | `date; source bashrc; cd /tmp; echo REACHED` | hangs, no output |
| C | `date; source bashrc; echo REACHED` | hangs, no output |
| D | `source bashrc; source env.sh; cd /tmp; echo REACHED` | exit 0, printed twice, under a second |

**Fix:** the `cd` moved behind the setup, for `enroot` and `native` alike;
`docker` keeps `-w` with a comment about the same hazard.

### R2 — mounts resolved through symlinks, the command line did not (`135ec9d`)

`_existing_paths` applied `Path.resolve()` to every mount while argv kept the
spelling it was given. `$HOME` on bwUniCluster is a symlink
(`/home/st/<user>` → `/pfs/data6/home/st/<user>`, check with
`readlink -f ~/eigenfrequencies`), so the repository was mounted under its real
name while the build was asked to run
`/home/st/.../turbine_runner/dtoo_cfd_build.py` — a path that does not exist
inside the container.

**Fix:** `os.path.abspath` instead of `Path.resolve` — absolute and normalised,
the same name on both sides of the mount.

While the shell looped (R1), the build never got far enough to look for the
script, which is why this surfaced only second.

### R3 — image staging was not repeatable (`a6cac25`)

`enroot create` on an already unpacked container aborts with `File already
exists`, which killed every interactive rerun in the same allocation. An existing
container is now skipped.

### R4 — the smoke's logs died with the node (`2561981`)

`local_scratch = "$TMPDIR"` puts every stage log on node-local scratch, deleted
when the allocation ends. Three debugging rounds were lost that way. The cfd
smoke now writes to the workspace; the production configs keep `$TMPDIR`.

### R5 — the image command script eval's our arguments (`e3d28b7`)

enroot passes the command and its arguments to the image's command script as
positional parameters. The dtOO image's script sources OpenFOAM's configuration,
and `etc/config.sh/functions` runs `eval` on those parameters at line 73:

```
/usr/lib/openfoam/openfoam2606/etc/config.sh/functions: eval: line 73:
  syntax error near unexpected token `"ok"'
  . …/config.sh/paraview python3.13 -c import dtOOPythonSWIG; print("ok")
```

The quotes around the Python code are gone. Two consequences: quoting is
destroyed, so a `;` inside our quoted payload becomes an outer-level separator
and fragments run in a half-built environment; and everything runs twice — the
long-standing observation behind commit `fae9a3d`, mechanism now identified.

**Fix:** `--rc cluster/enroot_rc.sh`, a file containing only `exec "$@"`.

### The two stages need different environments (`7ac482b`)

`DTOO_SETUP` sources both files and belongs to the stages that import
`dtOOPythonSWIG`. Removing the OpenFOAM line broke the **build**:
`cfd_build.log` fell from 3388 lines to 30, ending in
`ImportError: libTKFeat.so.7.9` — the dtOO environment alone does not put
OpenCASCADE on the library path.

The solve imports nothing and runs only OpenFOAM binaries, so it uses
`CFD_SOLVE_SETUP = ()`. Treating both stages as one was the underlying mistake.

### The solve's runtime is configurable (`c5d2bac`, `2a7fe8a`)

`solve_cfd` resolves its runtime from `{**dtoo_opts, **cfd_opts}`, so the cfd
section can override it for that stage alone:

```toml
[case.options.cfd]
runtime = "native"
setup = ["module load cae/openfoam/v2606"]
mpi_launcher = "mpiexec"
```

bwUniCluster ships v2606, the version the image carries.
`cluster/configs/tistos-smoke-cfd-native.toml` is that variant, with its own run
and scratch directories so both can be kept side by side. **Its first run also
ended 0/2 and produced no stage logs at all; the error text has not been read
yet.** That is the next thing to look at.

---

## 5. The open failure

`checkMesh` cannot load `libfiniteVolume.so` when the solve script runs it, even
though it starts fine when invoked directly in the same container.

`cluster/probe_solve_shell.sh` (7 rows, before the two `sh-file` rows were added)
reported **every** row as working — bare, with mounts, with `--rc`, with the
`cd`, with the exports, with the setup lines. So no single ingredient of the
invocation is the culprit.

The logs contradict that summary. Five `LD=` lines came out of three log files —
some variants ran more than once, **with different environments**:

```
…/openfoam2606/platforms/linux64GccDPInt32Opt/lib : …/lib/dummy      complete
/usr/lib64/mpi/gcc/openmpi4/lib64 : …/lib/dummy                      only dummy
/dtOO-install/lib:/usr/lib64:…:: …/lib/dummy                         only dummy
```

In the executions carrying only `lib/dummy`, `checkMesh` *must* fail. The probe
called them green because it looked for `rc=0` anywhere in the log and the other
execution succeeded. **The verdict logic is too lenient — it should require every
execution to succeed.**

The real solve has no such luck: `sh -e <script>` aborts on the first failing
command, and that exit code is what the stage reports.

Working hypothesis, unverified: **the double execution survives `--rc`, and one
of the two passes runs with an incomplete `LD_LIBRARY_PATH`.** The command that
would settle it:

```bash
grep -c '^rc=' /scratch/slurm_tmpdir/job_<id>/probe-solve-shell/*.log
```

Two per file means the double execution is still there.

---

## 6. Hypotheses that were wrong

Each looked convincing and cost time.

| # | Hypothesis | Verdict |
|---|---|---|
| W1 | A shared unpacked container store on the workspace saves 14-27 min per job (v2 §4 P1-2) | **Wrong twice.** The supporting measurement was node-local, not Lustre — v1 concludes the opposite. And `enroot create` measures 8.2 s, so the trade-off is moot. |
| W2 | `/dtOO-install/bin/env.sh` overwrites `LD_LIBRARY_PATH` | **Wrong.** It prepends (lines 102, 113). |
| W3 | The enroot branch needs a login shell, as native and docker use | **Wrong.** `bash -c` and `bash -lc` give byte-identical, complete `LD_LIBRARY_PATH`. |
| W4 | `enroot start` output does not survive redirection | **Wrong.** `echo HELLO` arrives on a tty, through a pipe and into a file alike. |
| W5 | 17 minutes without a result means the case is heavy and 30 min is too short | **Wrong.** It was the loop of R1; the export takes 144 s. |
| W6 | The 2-D `naca` case can serve as a cheap test vehicle | **Not as it stands.** `turbine_runner/cfd/` holds only `tistos_files`, `xml`, `boundaryData_RU_INLET`. The export would work; the solve has no case to run. |
| W7 | `timeout <n> <cmd> \| tail -3` safely bounds a looping command | **Wrong, three inconclusive rounds.** The container keeps the pipe's write end open, `tail` never sees EOF, nothing prints. Redirect to a file instead. |
| W8 | The reference runs one CFD per core (`start_de.py: cores_per_cfd = 1`) | **Wrong file.** That one instantiates `hydroFoil_problem()`, the 2-D predecessor with 3 parameters. The HPC variant is `--ntasks-per-node=32 --cpus-per-task=2` with `numberOfSubdomains = cpus_per_task`: 2 cores per CFD, many side by side. |
| W9 | Sourcing OpenFOAM's bashrc strips the library path, so dropping it from the setup fixes the solve | **Wrong, and it broke the build.** `probe_solve_env.sh` runs `checkMesh` fine in all six combinations including `both-no-rc`; removing the line cost the build its OpenCASCADE libraries. |
| W10 | The solve fails because it runs under `sh` while working stages run `bash` | **Wrong.** `/bin/sh` is a symlink to `bash`, and the library path is already gone in the `bash-c` row. |
| W11 | The host's `LD_LIBRARY_PATH` (from the python module `cluster_env.sh` loads) leaks in and overrides the image's | **Wrong.** The host value is `/opt/bwhpc/…/python/3.13.3_gnu_14.2/lib64:/opt/bwhpc/…/gnu/14.2.0/lib64`; none of it appears in the container's broken path. |
| W12 | The cluster's OpenFOAM module has to be loaded on the host for the container to work | **Wrong.** The container brings its own OpenFOAM; host modules matter only to the `native` runtime. |

---

## 7. Traps in the method, not in the code

- **Shell variables vanish between shells.** A lost `$W` turns `-m "$W:$W"` into
  `-m ":"` and `cd $W` into a `cd` to `$HOME`. Both look like container bugs.
  Source `cluster/interactive_setup.sh` in every shell.
- **`$TMPDIR` is per job.** Without it, `$TMPDIR` resolves to `/scratch` — the
  shared root — and `ls "$TMPDIR"` lists thousands of other people's files.
- **Node-local artifacts die with the allocation.** Anything to be read
  afterwards belongs on the workspace.
- **A frozen terminal mimics a hung command.** An accidental Ctrl-S stops the
  display while commands run and exit 0. Ctrl-Q restores it.
- **A probe script the container cannot see fails with 127 and no output** — the
  same signature as the bug. Two rows of `probe_solve_shell.sh` were invalid for
  exactly that reason: their inner scripts were written outside the mounts.
- **Interactive runs of the production config need ≥ 24 cores**
  (`islands 4 × mpi_ranks 6`). The smoke needs 12.
- **The container smoke scripts do not test the production path.**
  `submit_dtoo_enroot_smoke.sh` starts from the `.sqsh` through squashfuse, which
  production abandoned in `f76df43`. It appears to hang where the unpacked path
  takes seconds.

---

## 8. Open items

1. **Read the native-solve failure.** `tistos-smoke-cfd-native.toml` ended 0/2
   with no stage logs; the `error` field of its `results.jsonl` has not been
   looked at.
2. **Tighten `probe_solve_shell.sh`'s verdict** to require *every* execution to
   report `rc=0`, and to count executions per variant. The current logic hid the
   failing pass.
3. **Confirm or refute the surviving double execution** with the `grep -c '^rc='`
   command in §5.
4. **Make the smoke scripts mirror production** — `enroot create`, then start by
   name.
5. **Three unread job logs** on the cluster: `hydroflow_opt_6743978/79/80.out`,
   with job IDs above every generation recorded in v2 §2.
6. **gmsh in `~/pylibs`** never verified — needed for `combined` and
   `resonance_only`, irrelevant for `cfd_only`.
7. **`mpi_ranks = 6` versus the reference's 2 cores per CFD.** Worth revisiting
   once the solve runs; it cannot explain anything seen so far, because the dtOO
   phase is single-threaded gmsh.
