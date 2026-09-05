#!/usr/bin/env bash
# Probe: where does the CFD solve lose OpenFOAM's library path?
#
#     bash cluster/probe_solve_shell.sh
#
# Run it on a compute node with the dtOO container unpacked
# (`source cluster/interactive_setup.sh` does that).
#
# The geometry export works; the solve dies with
#
#     checkMesh: error while loading shared libraries: libfiniteVolume.so
#
# and cluster/probe_solve_env.sh already showed that `checkMesh` loads fine in
# every combination of --rc and setup lines when called from bash. One
# difference to every working case is left: the solve is the only stage that
# hands its payload to `sh` (physics.py: ["sh", "-e", script, case_dir, procs]),
# while the build runs python3.13 through the identical wrapper.
#
# Every variant below reproduces the production invocation exactly — the same two
# mounts, --root, --rc, both source lines, the cd and the three exports — and
# varies only what comes after `exec`. What matters per variant: does
# LD_LIBRARY_PATH still carry the OpenFOAM lib directory, and does checkMesh
# actually start.

CONTAINER="${CONTAINER:-dtOO}"
FOAM="${FOAM:-/usr/lib/openfoam/openfoam2606/etc/bashrc}"
DTOO_ENV="${DTOO_ENV:-/dtOO-install/bin/env.sh}"
FOAM_LIB="platforms/linux64GccDPInt32Opt/lib"
LIMIT="${LIMIT:-60}"
OUT="${TMPDIR:-/tmp}/probe-solve-shell"
REPO="${EIGENFREQUENCIES_REPO:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
RC="$REPO/cluster/enroot_rc.sh"

if ! enroot list 2>/dev/null | grep -qx "$CONTAINER"; then
    echo "no container '$CONTAINER' in ${ENROOT_DATA_PATH:-<default>}" >&2
    echo "run: source cluster/interactive_setup.sh" >&2
    exit 1
fi
[ -f "$RC" ] || { echo "no command script at $RC" >&2; exit 1; }

# The candidate directory of the last real run, so the mounts and the working
# directory are the ones production uses. Falls back to a scratch directory.
WORK="${WORK:-$WS/runs/tistos-smoke-cfd-local/baseline}"
if [ ! -d "$WORK" ]; then
    WORK="$OUT/work"
    echo "note: no candidate directory from a previous run, using $WORK"
fi
mkdir -p "$OUT" "$WORK"

# A script file for the variant that runs one, mirroring `sh -e <script>`.
cat > "$OUT/inner.sh" <<EOF
echo "LD=\$LD_LIBRARY_PATH"
checkMesh -help >/dev/null 2>&1
echo "rc=\$?"
EOF

echo "container=$CONTAINER  work=$WORK  logs=$OUT"
echo
printf '%-14s %-10s %-10s %s\n' "variant" "foam-lib" "checkMesh" "note"
printf '%-14s %-10s %-10s %s\n' "-------------" "--------" "---------" "----"

probe() {
    label="$1"; payload="$2"
    log="$OUT/$label.log"

    timeout "$LIMIT" enroot start \
        -m "$REPO:$REPO" -m "$WORK:$WORK" \
        --root --rc "$RC" "$CONTAINER" \
        bash -c ". $FOAM; . $DTOO_ENV; cd $WORK; export MPI_LAUNCHER=mpirun; export OMPI_ALLOW_RUN_AS_ROOT=1; export OMPI_ALLOW_RUN_AS_ROOT_CONFIRM=1; $payload" \
        > "$log" 2>&1

    if grep -q "LD=.*$FOAM_LIB\(:\|$\)" "$log"; then lib="yes"; else lib="NO"; fi
    if grep -q "^rc=0" "$log"; then run="yes"; else run="NO"; fi
    note="$(grep -m1 -E "loading shared libraries|not found|^/bin/sh|busybox|dash|bash" "$log" | cut -c1-46)"
    printf '%-14s %-10s %-10s %s\n' "$label" "$lib" "$run" "$note"
}

# Is the environment intact in the shell that production builds?
probe "bash-c" "exec bash -c 'echo LD=\$LD_LIBRARY_PATH; checkMesh -help >/dev/null 2>&1; echo rc=\$?'"

# Does `sh -c` lose it? This is the shell the solve script runs in.
probe "sh-c" "exec sh -c 'echo LD=\$LD_LIBRARY_PATH; checkMesh -help >/dev/null 2>&1; echo rc=\$?'"

# `sh -e <file>` — exactly how the solve script is invoked.
probe "sh-script" "exec sh -e $OUT/inner.sh"

# What is /bin/sh in this image?
probe "sh-identity" "exec sh -c 'echo LD=\$LD_LIBRARY_PATH; ls -l /bin/sh; readlink -f /bin/sh; echo rc=0'"

echo
echo "logs in $OUT"
echo
echo "foam-lib yes for bash-c and NO for sh-c  -> sh drops it; run the solve script with bash."
echo "foam-lib yes everywhere but checkMesh NO -> not the shell; look at the working directory"
echo "                                            and the mounts in the per-variant logs."
