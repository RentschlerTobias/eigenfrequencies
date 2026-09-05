#!/usr/bin/env bash
# Probe: which ingredient of the solve invocation costs OpenFOAM its library path?
#
#     bash cluster/probe_solve_shell.sh
#
# Run it on a compute node with the dtOO container unpacked
# (`source cluster/interactive_setup.sh` does that).
#
# Established so far:
#
#   * `enroot start --root dtOO checkMesh -help` works. The image configures
#     OpenFOAM by itself and LD_LIBRARY_PATH arrives complete.
#   * the production solve fails with
#     `checkMesh: error while loading shared libraries: libfiniteVolume.so`,
#     and it still does with no setup lines at all.
#
# So the cause is one of the remaining differences: the two mounts, the replaced
# command script (--rc), the cd into the candidate directory, or the exports.
# Each row below adds one of them to the bare call that works. The first row
# that turns `foam-lib` to NO is the culprit.
#
# Payload is the same everywhere: report LD_LIBRARY_PATH, then try to start
# checkMesh and report its exit status.

CONTAINER="${CONTAINER:-dtOO}"
FOAM_LIB="platforms/linux64GccDPInt32Opt/lib"
FOAM="${FOAM:-/usr/lib/openfoam/openfoam2606/etc/bashrc}"
DTOO_ENV="${DTOO_ENV:-/dtOO-install/bin/env.sh}"
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

WORK="${WORK:-$WS/runs/tistos-smoke-cfd-local/baseline}"
[ -d "$WORK" ] || { WORK="$OUT/work"; echo "note: using $WORK"; }
mkdir -p "$OUT" "$WORK"

REPORT='echo LD=$LD_LIBRARY_PATH; checkMesh -help >/dev/null 2>&1; echo rc=$?'
EXPORTS='export MPI_LAUNCHER=mpirun; export OMPI_ALLOW_RUN_AS_ROOT=1; export OMPI_ALLOW_RUN_AS_ROOT_CONFIRM=1; '

echo "container=$CONTAINER  work=$WORK  logs=$OUT"
echo
printf '%-22s %-10s %-10s %s\n' "variant" "foam-lib" "checkMesh" "first LD entries"
printf '%-22s %-10s %-10s %s\n' "----------------------" "--------" "---------" "----------------"

# $1 label, $2 "yes"/"no" mounts, $3 "yes"/"no" --rc, $4 prefix inside bash -c
probe() {
    label="$1"; mounts="$2"; use_rc="$3"; prefix="$4"
    log="$OUT/$label.log"

    args=()
    [ "$mounts" = "yes" ] && args+=(-m "$REPO:$REPO" -m "$WORK:$WORK")
    args+=(--root)
    [ "$use_rc" = "yes" ] && args+=(--rc "$RC")

    timeout "$LIMIT" enroot start "${args[@]}" "$CONTAINER" \
        bash -c "${prefix}${REPORT}" > "$log" 2>&1

    if grep -q "LD=.*$FOAM_LIB\(:\|\$\)" "$log"; then lib="yes"; else lib="NO"; fi
    if grep -q "^rc=0" "$log"; then run="yes"; else run="NO"; fi
    head="$(grep -m1 '^LD=' "$log" | cut -c1-60)"
    printf '%-22s %-10s %-10s %s\n' "$label" "$lib" "$run" "${head:-<no LD line>}"
}

probe "bare"              "no"  "no"  ""
probe "rc"                "no"  "yes" ""
probe "mounts"            "yes" "no"  ""
probe "mounts+rc"         "yes" "yes" ""
probe "mounts+rc+cd"      "yes" "yes" "cd $WORK; "
probe "production"        "yes" "yes" "cd $WORK; $EXPORTS"
probe "production+setup"  "yes" "yes" ". $FOAM; . $DTOO_ENV; cd $WORK; $EXPORTS"

echo
echo "logs in $OUT"
echo
echo "The first row with foam-lib NO names the ingredient that costs the library path."
