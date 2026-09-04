#!/usr/bin/env bash
# Probe: which combination of --rc and setup lines lets an OpenFOAM utility find
# its libraries, and does it run once or twice?
#
#     bash cluster/probe_solve_env.sh
#
# Run it on a compute node with the dtOO container unpacked
# (`source cluster/interactive_setup.sh` does that).
#
# Every variant runs `checkMesh -help` and echoes a marker. Three numbers decide
# it: whether the marker appears at all, how often (once = one execution, twice =
# the image command script eval'ing our arguments a second time), and whether the
# dynamic loader complained about libfiniteVolume.so.
#
# The point of the exercise: the image supplies a complete OpenFOAM environment
# on its own — `enroot start --root dtOO checkMesh -help` works with no setup at
# all. Sourcing OpenFOAM's own bashrc on top of that appears to *remove* the main
# library directory from LD_LIBRARY_PATH. If that is what the table shows, the
# bashrc has to go from DTOO_SETUP in physics.py.

CONTAINER="${CONTAINER:-dtOO}"
FOAM="${FOAM:-/usr/lib/openfoam/openfoam2606/etc/bashrc}"
DTOO_ENV="${DTOO_ENV:-/dtOO-install/bin/env.sh}"
OUT="${TMPDIR:-/tmp}/probe-solve-env"

if ! enroot list 2>/dev/null | grep -qx "$CONTAINER"; then
    echo "no container '$CONTAINER' in ${ENROOT_DATA_PATH:-<default>}" >&2
    echo "run: source cluster/interactive_setup.sh" >&2
    exit 1
fi

mkdir -p "$OUT"
# The replacement command script has to resolve inside the container, so it goes
# into a directory that is mounted below.
printf 'exec "$@"\n' > "$OUT/rc.sh"

printf '%-34s %-8s %-8s %s\n' "variant" "marker" "count" "loader error"
printf '%-34s %-8s %-8s %s\n' "----------------------------------" "------" "-----" "------------"

probe() {
    label="$1"; use_rc="$2"; setup="$3"
    log="$OUT/${label// /_}.log"

    rc_args=""
    [ "$use_rc" = "yes" ] && rc_args="--rc $OUT/rc.sh"

    payload="${setup}checkMesh -help >/dev/null 2>&1 && echo MARKER-$label"

    # shellcheck disable=SC2086
    timeout 60 enroot start --root -m "$OUT:$OUT" $rc_args "$CONTAINER" \
        bash -c "$payload" > "$log" 2>&1

    count=$(grep -c "MARKER-$label" "$log")
    if grep -q "libfiniteVolume" "$log"; then loader="yes"; else loader="no"; fi
    if [ "$count" -gt 0 ]; then marker="yes"; else marker="NO"; fi
    printf '%-34s %-8s %-8s %s\n' "$label" "$marker" "$count" "$loader"
}

probe "no-setup-no-rc"      "no"  ""
probe "no-setup-with-rc"    "yes" ""
probe "dtoo-only-with-rc"   "yes" ". $DTOO_ENV; "
probe "foam-only-with-rc"   "yes" ". $FOAM; "
probe "both-with-rc"        "yes" ". $FOAM; . $DTOO_ENV; "
probe "both-no-rc"          "no"  ". $FOAM; . $DTOO_ENV; "

echo
echo "logs in $OUT"
echo
echo "count 1 everywhere  -> --rc removed the double execution."
echo "loader error only where the OpenFOAM bashrc is sourced"
echo "                    -> drop that line from DTOO_SETUP, keep the dtOO env.sh."
