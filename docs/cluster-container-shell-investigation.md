# Why no candidate ever finished on bwUniCluster — investigation log, 2026-09-04

**Status:** two root causes found and fixed, one failure still open.
**Scope:** the container shell that `physics.py` builds for every dtOO stage.
**Companion:** `docs/cluster-dtoo-enroot-befund-v2.md` §4 P0-3 records the symptom;
this file records the investigation, including the hypotheses that turned out to
be wrong. Those are the expensive part to rediscover.

Written after a session that went from "the pipeline hangs and produces nothing"
to "the geometry export completes in 144 s and the solve fails with a readable
error". Every claim below is backed by a measurement taken on the cluster on
2026-09-04; where a claim is inference rather than measurement, it says so.

---

## 1. The symptom we started from

A `cfd_only` evaluation produced **nothing at all**: no artifact, no log line, no
error message. It sat until its 1800 s timeout and was recorded as a failure with
an empty log. Two candidates ran for 17 minutes and left one `request.json` each.

Critically, per the repository owner: **no case had ever completed with this
setup**. This was never a regression — the chain had never worked end to end.

The reference implementation puts the same tistos case (3-D, 30 parameters)
through mesh *and* solve for several individuals inside a 30-minute `dev_cpu_il`
window, so "it is simply a heavy case" was never a credible explanation.

---

## 2. Root causes found and fixed

### R1 — `cd` before sourcing loops the container shell (commit `519ebf1`)

`Runtime.command` built every container command as

```
bash -c "cd <workdir>; source .../etc/bashrc; source /dtOO-install/bin/env.sh; exec <payload>"
```

Changing directory *before* sourcing OpenFOAM's bashrc makes the shell reprint
everything ahead of the source several times a second and never return. The
trailing `exec` — added earlier precisely to stop a double execution — never
helps, because control never reaches it.

Measured with `cluster/probe_openfoam_cd_order.sh`:

| variant | payload | result |
|---|---|---|
| A | `cd /tmp; date; source bashrc; echo REACHED` | 109 lines in 20 s, `REACHED` never printed |
| B | `date; source bashrc; cd /tmp; echo REACHED` | hangs, no output |
| C | `date; source bashrc; echo REACHED` | hangs, no output |
| D | `source bashrc; source env.sh; cd /tmp; echo REACHED` | exit 0, `REACHED` printed twice, under a second |

Only D completes — both environments sourced first, directory change afterwards.
Sourcing the OpenFOAM bashrc *alone* (B and C) hangs as well.

**Fix:** the `cd` moved from ahead of the setup to behind it, for the `enroot`
and `native` branches alike. `docker` keeps `-w` and carries a comment about the
same hazard. Regression test covers all three runtimes.

### R2 — mounts resolved through symlinks, the command line did not (commit `135ec9d`)

`_existing_paths` applied `Path.resolve()` to every mount while the argv kept the
spelling it was given. On bwUniCluster `$HOME` is a symlink:

```
/home/st/<user>  ->  /pfs/data6/home/st/<user>
```

So the repository was mounted as `/pfs/data6/.../eigenfrequencies` while the
build was asked to run
`/home/st/.../eigenfrequencies/turbine_runner/dtoo_cfd_build.py` — a path that
does not exist inside the container. Every cfd build died with

```
python3.13: can't open file '.../turbine_runner/dtoo_cfd_build.py': [Errno 2] No such file or directory
```

pointing at a file plainly present on the host.

**Fix:** `os.path.abspath` instead of `Path.resolve` — absolute and normalised,
but the same name on both sides of the mount.

**Why it surfaced only second:** while the shell looped (R1), the build never got
far enough to look for the script.

### R3 — image staging was not repeatable (commit `a6cac25`)

`enroot create` on an already unpacked container aborts with `File already
exists`, which killed every interactive rerun in the same allocation. A batch job
gets a fresh `$TMPDIR` and never sees it. Now an existing container is treated as
success and skipped.

### R4 — the smoke's own logs died with the node (commit `2561981`)

`local_scratch = "$TMPDIR"` puts every stage log on node-local scratch, which is
deleted when the allocation ends. Three debugging rounds were lost this way: the
run reported an error and the file explaining it was already gone.
`cluster/configs/tistos-smoke-cfd.toml` now points `local_scratch` at the
workspace. The production configs keep `$TMPDIR` — a smoke exists to be read
afterwards, a production run does not.

---

## 3. Where the chain stands after R1 and R2

The dtOO geometry export **works**:

```
timings.total = 144 s          (candidate "baseline")
hydroflow_ru_gridGmsh.msh      22 353 306 bytes
logs/cfd_build.log             334 392 bytes
tistos_ru_of_n_hydroflow/      the OpenFOAM case, created
```

22.3 MB matches the 21.8 MB the same design produced locally on 2026-08-28. The
export is not slow and not broken; it never ran before.

The failure moved one stage further:

```
"error": "RuntimeError: CFD evaluation failed: cfd solve: exit 127"
logs/cfd_solve.log             0 bytes
tistos_ru_of_n_hydroflow/log.checkMesh:
  checkMesh: error while loading shared libraries: libfiniteVolume.so:
  cannot open shared object file: No such file or directory
```

`cfd_solve.log` is empty because the solve script redirects each command's stdout
*and* stderr into its own `log.<command>` inside the case directory — so the
shell's own "cannot open shared object" message lands there too, and nothing
reaches the stage log. Exit 127 here comes from the dynamic loader, not from
"command not found".

---

## 4. The mechanism behind the loops

Running a payload with quotes in it exposed what had been guessed at for weeks:

```
/usr/lib/openfoam/openfoam2606/etc/config.sh/functions: eval: line 73:
  syntax error near unexpected token `"ok"'
  . /usr/lib/openfoam/openfoam2606/etc/config.sh/paraview python3.13 -c import dtOOPythonSWIG; print("ok")
```

OpenFOAM's `etc/config.sh/functions` runs an **`eval` on the command-line
arguments** at line 73. Note the quotes around the Python code are gone — the
arguments were flattened and re-evaluated with their quoting destroyed.

The container start path passes our command into the sourcing of OpenFOAM's
configuration as positional parameters, and that eval re-runs it. This is the
long-standing observation recorded in commit `fae9a3d` — "sourcing OpenFOAM's
bashrc leaves the shell in a state where it runs its own command string a SECOND
time" — with the mechanism finally identified. If the re-evaluated string itself
sources the bashrc again, the result is the endless loop of R1.

**Practical consequences:**

- A payload containing quotes can be mangled before it ever runs.
- `exec` on the last statement limits the damage but does not prevent the eval.
- A command passed as a single argument (a script *path* rather than a script
  *string*) has no quoting to lose. Untested as a general fix.

---

## 5. What the container actually provides

Measured directly, without any sourcing:

- `enroot start --root dtOO checkMesh -help` **works** and reports
  `Using: OpenFOAM-2606`. The OpenFOAM environment is complete in the image.
- `LD_LIBRARY_PATH` is identical for `bash -c` and `bash -lc`, and already
  contains `/usr/lib/openfoam/openfoam2606/platforms/linux64GccDPInt32Opt/lib`.
  A login shell changes nothing.
- `enroot start --root dtOO python3.13 -c 'import dtOOPythonSWIG'` **fails** with
  `ImportError: libTKFeat.so.7.9`. The dtOO bindings still need
  `/dtOO-install/bin/env.sh` for the OpenCASCADE libraries.
- Binaries present: `mpirun`, `simpleFoam`, `checkMesh`, `decomposePar`,
  `reconstructPar`. **`mpiexec` is absent** — which confirms v2 §4 P0-1 and the
  `mpi_launcher = "mpirun"` config fix.

### The setup lines are not the culprit

`cluster/probe_solve_env.sh` ran `checkMesh -help` in six combinations of
`--rc` and setup lines:

| variant | marker | count | loader error |
|---|---|---|---|
| no-setup-no-rc | yes | 2 | no |
| no-setup-with-rc | yes | 2 | no |
| dtoo-only-with-rc | yes | 1 | no |
| foam-only-with-rc | yes | 1 | no |
| both-with-rc | yes | 1 | no |
| both-no-rc | yes | 1 | no |

**`checkMesh` works in every one of them**, including `both-no-rc`, which is
what production did before `e3d28b7`. So sourcing the OpenFOAM bashrc does not
cost the library path, and the hypothesis that `DTOO_SETUP` should lose that
line is unsupported.

What distinguishes the real solve from every variant above is that it does not
call `checkMesh` directly: it runs `sh -e <script> <case_dir> <procs>`, and the
script calls `checkMesh` from there. That path has never been observed.

### R5 — sourcing OpenFOAM's bashrc strips the library path (commit pending)

`cluster/probe_solve_shell.sh`, reproducing the production invocation exactly,
reports after both source lines:

```
LD=/dtOO-install/lib:/usr/lib64:/usr/lib64:/usr/lib64::/usr/lib64/mpi/gcc/openmpi4/lib64:/usr/lib/openfoam/openfoam2606/platforms/linux64GccDPInt32Opt/lib/dummy
rc=127
```

Every OpenFOAM entry is gone except `lib/dummy`; what remains is the dtOO
additions plus the two base entries. The bashrc strips its own paths before
rebuilding them, concludes the environment is already set up — which it is, the
image exports it — and puts nothing back. `checkMesh` then cannot load
`libfiniteVolume.so`, and `sh -e` aborts with 127 before writing anything.

The first attempt — `DTOO_SETUP` keeping only `/dtOO-install/bin/env.sh` — broke
the *build* instead: `cfd_build.log` fell from 3388 lines to 30 and ended with

```
ImportError: libTKFeat.so.7.9: cannot open shared object file
```

The dtOO environment alone does not put OpenCASCADE on the library path either;
it needs what the bashrc leaves behind. So the two stages genuinely need
different environments, and treating them as one was the underlying mistake:

- **build** (`python3.13 dtoo_cfd_build.py`, imports `dtOOPythonSWIG`) keeps
  `DTOO_SETUP`, both sources, in that order.
- **solve** (`sh -e sbatch.tistos_ru_of.sh`, imports nothing, runs only OpenFOAM
  binaries) uses `CFD_SOLVE_SETUP = ()` — no setup at all, because the image
  already configures OpenFOAM and sourcing its bashrc undoes that.

Note this contradicts W9 above, which was drawn from `probe_solve_env.sh`: there
`checkMesh` survived the same two source lines. The difference between the two
probes is the mounts, the `cd` into the candidate directory and the three
exports; which of them tips the bashrc into the stripping branch was not chased
further once the fix was clear.

This is where the investigation stopped for lack of an allocation. The next run
will say more by itself: since `9b5108c` every stage log opens with the exact
argv, and `StageError` carries it too, so `results.json` names the command that
failed instead of only its exit code.

---

## 6. Hypotheses that were wrong

Recorded because each one looked convincing and cost time.

| # | Hypothesis | Verdict |
|---|---|---|
| W1 | A shared unpacked container store on the workspace (`$WS/enroot-data`) saves a per-job cost of 14-27 minutes (v2 §4 P1-2) | **Wrong twice over.** The supporting measurement was node-local, not Lustre (see `docs/cluster-dtoo-enroot-befund.md`, which concludes the opposite). And `enroot create` was then measured at **8.2 s cold, 3.8 s warm** for the 5.8 GB image — the whole trade-off is moot. |
| W2 | `/dtOO-install/bin/env.sh` overwrites `LD_LIBRARY_PATH` and wipes OpenFOAM's entries | **Wrong.** It prepends: `export LD_LIBRARY_PATH="${THRDPARTY_PATH}:${LD_LIBRARY_PATH}"` (lines 101-104). |
| W3 | The enroot branch needs a login shell (`bash -lc`) like the native and docker branches, because the image sets up its environment in `/etc/profile.d` | **Wrong.** `bash -c` and `bash -lc` produce byte-identical `LD_LIBRARY_PATH`, both complete. |
| W4 | `enroot start` output does not survive redirection into a file or a pipe | **Wrong.** `echo HELLO` arrives on a tty, through a pipe and into a file alike. The apparent silence had two other causes: an empty log is what a loop that never reaches its first `echo` produces, and `timeout … \| tail` swallows everything (see W7). |
| W5 | 17 minutes without a result means the case is heavy and `dev_cpu_il`'s 30-minute limit is too small | **Wrong.** It was the loop of R1. The export takes 144 s. |
| W6 | The 2-D `naca` case can serve as a cheap test vehicle for the same chain | **Not possible as it stands.** `turbine_runner/cfd/` contains only `tistos_files`, `xml` and `boundaryData_RU_INLET`. There is no OpenFOAM case for naca — the geometry export would work (`adapters/machines/naca.yaml`: "builds gridGmsh in the container in seconds"), the solve has nothing to run. |
| W7 | `timeout <n> <cmd> \| tail -3` is a safe way to bound a looping command | **Wrong, and it cost three inconclusive rounds.** `timeout` signals the process, the container keeps the pipe's write end open, `tail` never sees EOF and prints nothing. Redirect to a file and inspect the file instead. |
| W10 | The solve fails because it runs under `sh` while every working stage runs `bash` | **Wrong.** `/bin/sh` in the dtOO image is a 4-character symlink — to `bash`. And `cluster/probe_solve_shell.sh` shows the library path already gone in the `bash-c` variant, before any `sh` is involved. |
| W9 | Sourcing OpenFOAM's bashrc removes the main library directory from `LD_LIBRARY_PATH`, so dropping it from `DTOO_SETUP` fixes the solve | **Wrong.** `cluster/probe_solve_env.sh` runs `checkMesh` fine in all six combinations of `--rc` and setup lines, `both-no-rc` included. The difference in the real solve is `sh -e <script>`, not the setup. |
| W8 | The reference framework runs one CFD per core (`start_de.py: cores_per_cfd = 1`) | **Wrong file.** That `start_de.py` instantiates `hydroFoil_problem()`, the 2-D predecessor with 3 parameters. The HPC variant asks for `--ntasks-per-node=32 --cpus-per-task=2` and sets `numberOfSubdomains = cpus_per_task`: **2 cores per CFD, many CFDs side by side**. The 32 is concurrency, not ranks. |

---

## 7. Traps in the method, not in the code

These produced misleading evidence and are worth recognising early.

- **Shell variables vanish between shells.** Losing `$W` turns `-m "$W:$W"` into
  `-m ":"` and `cd $W` into a `cd` to `$HOME`. Both look like container bugs.
  `cluster/interactive_setup.sh` exists to make this a single command.
- **`$TMPDIR` is per job.** A shell without it resolves `$TMPDIR` to `/scratch`,
  the shared root — `ls "$TMPDIR"` then lists thousands of other people's files
  and nothing makes sense.
- **Node-local artifacts die with the allocation.** Anything worth reading after
  the fact belongs on the workspace (R4).
- **A frozen terminal mimics a hung command.** An accidental Ctrl-S stops the
  display while commands run and exit 0. Ctrl-Q restores it.
- **Interactive runs of the production config need ≥ 24 cores** —
  `islands 4 × mpi_ranks 6` is the floor below which the resource check refuses
  to start. The smoke config needs 12.
- **The container smoke scripts do not test the production path.**
  `submit_dtoo_enroot_smoke.sh` starts from the `.sqsh` through squashfuse, which
  the production path abandoned in `f76df43`. It appears to hang where the
  unpacked path takes seconds. Still open.

---

## 8. Open items

1. **The solve's missing libraries.** Test in §5; if it passes, drop the
   OpenFOAM line from `DTOO_SETUP` in `physics.py`.
2. **Smoke scripts use the squashfuse path.** Both should mirror production:
   `enroot create`, then start by name.
3. **Three unread job logs** on the cluster: `hydroflow_opt_6743978/79/80.out`,
   with job IDs above every generation recorded in v2 §2.
4. **gmsh in `~/pylibs`** never verified — needed for `combined` and
   `resonance_only`, irrelevant for `cfd_only`.
5. **`mpi_ranks = 6` versus the reference's 2 cores per CFD.** Worth revisiting
   once the solve runs, but it cannot explain anything seen so far: the dtOO
   phase is single-threaded gmsh.
