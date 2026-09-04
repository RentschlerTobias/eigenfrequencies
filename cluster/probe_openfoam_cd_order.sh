#!/usr/bin/env bash
# Probe: does changing directory *before* sourcing OpenFOAM's bashrc send the
# container shell into an endless re-execution loop?
#
#     bash cluster/probe_openfoam_cd_order.sh
#
# Run it on a compute node with the dtOO container unpacked
# (`source cluster/interactive_setup.sh` does that).
#
# Background: a candidate evaluation produces nothing at all — no artifacts, no
# log lines, no error — and dies on its 1800 s timeout. Measured by hand, a
# container shell started as
#
#     bash -c "cd <workdir>; source .../etc/bashrc; ..."
#
# prints the marker *before* the source over and over, several times a second,
# and never reaches the marker after it. Without the `cd` the identical sequence
# finishes in well under a second. physics.py builds exactly the first form
# (Runtime.command: `f"cd {workdir}; {script}"`), which would explain why no
# case has ever completed with this setup.
#
# Each variant below runs with a timeout and its own log. What matters is the
# line count: a handful means it ran through, hundreds mean it looped.

CONTAINER="${CONTAINER:-dtOO}"
FOAM="${FOAM:-/usr/lib/openfoam/openfoam2606/etc/bashrc}"
DTOO_ENV="${DTOO_ENV:-/dtOO-install/bin/env.sh}"
LIMIT="${LIMIT:-20}"
OUT="${TMPDIR:-/tmp}/probe-cd-order"

mkdir -p "$OUT"

if ! enroot list 2>/dev/null | grep -qx "$CONTAINER"; then
    echo "no container '$CONTAINER' in ${ENROOT_DATA_PATH:-<default>}" >&2
    echo "run: source cluster/interactive_setup.sh" >&2
    exit 1
fi

echo "container=$CONTAINER  timeout=${LIMIT}s  logs=$OUT"
echo

probe() {
    label="$1"
    payload="$2"
    log="$OUT/$label.log"
    timeout "$LIMIT" enroot start --root "$CONTAINER" bash -c "$payload" > "$log" 2>&1
    status=$?
    lines=$(wc -l < "$log")
    if [ "$status" -eq 124 ]; then
        verdict="TIMED OUT — looped or hung"
    elif [ "$lines" -gt 20 ]; then
        verdict="repeated output — looped"
    elif grep -q REACHED "$log"; then
        verdict="reached the end"
    else
        verdict="ended without reaching the end"
    fi
    printf '%-18s exit=%-4s lines=%-6s %s\n' "$label" "$status" "$lines" "$verdict"
    tail -2 "$log" | sed 's/^/                   /'
    echo
}

# The production form: cd first, then source.
probe "A-cd-then-source" "cd /tmp; date +'%T A-before'; source $FOAM; echo A-REACHED"

# The candidate fix: source first, then cd.
probe "B-source-then-cd" "date +'%T B-before'; source $FOAM; cd /tmp; echo B-REACHED"

# Control: no cd at all. This is the form the dtOO smoke test uses, and it works.
probe "C-no-cd" "date +'%T C-before'; source $FOAM; echo C-REACHED"

# The full fixed sequence, both environments, as physics.py would build it.
probe "D-full-fixed" "source $FOAM; source $DTOO_ENV; cd /tmp; echo D-REACHED"

echo "A looped while B, C and D reached the end  ->  the cd before the source is the cause."
echo "All four looped                            ->  the cd is innocent, look at the sourcing itself."
