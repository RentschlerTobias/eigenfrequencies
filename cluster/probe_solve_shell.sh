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
# checkMesh and report its exit status. Each row reports how many times the
# payload ran and how many of those runs had rc=0; the row is PASS only when
# the payload ran at least once and every run exited 0, and the script exits
# 1 overall if any row is FAIL.

CONTAINER="${CONTAINER:-dtOO}"
FOAM_LIB="platforms/linux64GccDPInt32Opt/lib"
FOAM="${FOAM:-/usr/lib/openfoam/openfoam2606/etc/bashrc}"
DTOO_ENV="${DTOO_ENV:-/dtOO-install/bin/env.sh}"
LIMIT="${LIMIT:-60}"
OUT="${PROBE_OUT:-${TMPDIR:-/tmp}/probe-solve-shell}"
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
printf '%-22s %-10s %-11s %-5s %-14s %s\n' "variant" "foam-lib" "executions" "rc0" "VERDICT" "first LD entries"
printf '%-22s %-10s %-11s %-5s %-14s %s\n' "----------------------" "--------" "-----------" "----" "--------------" "----------------"

# Aggregate verdict across all probes: any FAIL -> overall exit 1.
ANY_FAIL=0

# $1 = log file. Prints "executions=<n>  rc0=<k>  VERDICT=PASS|FAIL" to stdout.
# Returns 0 iff n>=1 and every "^rc=" line equals 0; returns 1 otherwise.
# Self-contained: only $1 and grep are referenced, so sed extraction works.
verdict_of() {
    local log="$1"
    local n k
    n="$(grep -c '^rc=' "$log" 2>/dev/null || true)"
    k="$(grep -c '^rc=0$' "$log" 2>/dev/null || true)"
    n="${n:-0}"
    k="${k:-0}"
    if [ "$n" -ge 1 ] && [ "$n" -eq "$k" ]; then
        printf 'executions=%s  rc0=%s  VERDICT=PASS\n' "$n" "$k"
        return 0
    else
        printf 'executions=%s  rc0=%s  VERDICT=FAIL\n' "$n" "$k"
        return 1
    fi
}

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
    summary="$(verdict_of "$log")"
    vrc=$?
    [ "$vrc" -ne 0 ] && ANY_FAIL=1
    execs="${summary#executions=}"
    execs="${execs%  rc0=*}"
    rc0="${summary#*  rc0=}"
    rc0="${rc0%  VERDICT=*}"
    verdict="${summary##*VERDICT=}"
    head="$(grep -m1 '^LD=' "$log" | cut -c1-60)"
    printf '%-22s %-10s %-11s %-5s %-14s %s\n' "$label" "$lib" "$execs" "$rc0" "$verdict" "${head:-<no LD line>}"
}

probe "bare"              "no"  "no"  ""
probe "rc"                "no"  "yes" ""
probe "mounts"            "yes" "no"  ""
probe "mounts+rc"         "yes" "yes" ""
probe "mounts+rc+cd"      "yes" "yes" "cd $WORK; "
probe "production"        "yes" "yes" "cd $WORK; $EXPORTS"
probe "production+setup"  "yes" "yes" ". $FOAM; . $DTOO_ENV; cd $WORK; $EXPORTS"

# The real solve does not call checkMesh itself: it hands a script to `sh -e`,
# and that script changes into the OpenFOAM case directory before running
# anything. Two directory changes in two shells — the part the rows above never
# covered.
# The scripts go under $WORK, not $OUT: only $WORK and $REPO are mounted, and a
# script the container cannot see fails with 127 and no output — the same
# signature as the bug, from a different cause. That mistake cost one round.
CASE="$(find "$WORK" -maxdepth 1 -type d -name 'tistos_ru_of_*' | head -1)"
if [ -n "$CASE" ]; then
    printf 'echo LD=$LD_LIBRARY_PATH\ncheckMesh -help >/dev/null 2>&1\necho rc=$?\n' > "$WORK/probe-plain.sh"
    printf 'cd %s\necho LD=$LD_LIBRARY_PATH\ncheckMesh -help >/dev/null 2>&1\necho rc=$?\n' "$CASE" > "$WORK/probe-incase.sh"
    probe "sh-file"           "yes" "yes" "cd $WORK; $EXPORTS exec sh -e $WORK/probe-plain.sh; "
    probe "sh-file-in-case"   "yes" "yes" "cd $WORK; $EXPORTS exec sh -e $WORK/probe-incase.sh; "
else
    echo "note: no tistos_ru_of_* case directory under $WORK — skipping the sh-file rows"
fi

echo
echo "logs in $OUT"
echo
echo "The first row with foam-lib NO names the ingredient that costs the library path."

exit "$ANY_FAIL"
