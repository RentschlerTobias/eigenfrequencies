#!/usr/bin/env bash
# One CFD case build, in the container, with the output on your screen.
#
#     bash cluster/diagnose_cfd_build.sh
#
# Run it on an interactive node (salloc). The production path hides this: it
# captures the container's output and writes it to a log in node-local scratch,
# which disappears with the job — so a stage that takes 30 minutes and then times
# out leaves nothing behind to explain itself.
#
# What we are trying to find out: the de_framework builds mesh *and* solve in
# ~15 minutes on a single core (start_de.py: cores_per_cfd = 1), while our build
# alone exceeds 1800 s. The timestamps below say which part accounts for it.
#
# The command is ONE `bash -c` line with the steps joined by ';', exactly as
# physics.py builds it. Not a script file: OpenFOAM's etc/bashrc locates itself
# through BASH_SOURCE, and when sourced from a script that points at *our*
# script, which it then sources again — an infinite loop that prints the first
# line forever. With `bash -c` there is no BASH_SOURCE and the problem does not
# arise, which is why the production path never hit it.

set -uo pipefail

REPO="${EIGENFREQUENCIES_REPO:-$HOME/eigenfrequencies}"
IMAGES="${ENROOT_IMAGES:-${WS:?set WS or ENROOT_IMAGES}/enroot-images}"
IMAGE="$IMAGES/dtOO.sqsh"
WORK="${WORK:-${TMPDIR:-/tmp}/cfd-diagnose}"
STATE="${STATE:-diag}"

[[ -f "$IMAGE" ]] || { echo "no image at $IMAGE" >&2; exit 1; }

echo "=== repo=$REPO"
echo "=== image=$IMAGE"
echo "=== work=$WORK"

rm -rf "$WORK"
mkdir -p "$WORK"
cd "$WORK"

# The case inputs have to sit next to the case: machine.xml includes ./xml/...
# relative to the working directory.
cp -r "$REPO"/turbine_runner/cfd/{tistos_files,xml,boundaryData_RU_INLET} .

# Empty design = the template geometry, which is what candidate "baseline" uses.
echo '{}' > design.json

# Output goes to a file, never to the terminal, and the container runs in the
# FOREGROUND. Both are deliberate, and both were wrong in the first version:
#
#   * backgrounding it put the container out of reach of Ctrl-C, so interrupting
#     killed only this script while the container kept writing to the terminal;
#   * streaming to the terminal made the session unusable — you cannot read what
#     you are typing, so you cannot even stop it.
#
# Foreground plus redirection gives both back: Ctrl-C works, the terminal stays
# readable, and the log survives the interrupt. Watch it from a second window.
# The image is UNPACKED, not mounted. enroot mounts a .sqsh through squashfuse,
# a userspace FUSE mount that decompresses every read in one process: measured
# at 37% CPU on a compute node while CreateStates, 8 seconds against an unpacked
# image, had not finished after 20 minutes. `enroot create` writes a plain
# directory once and the reads become ordinary filesystem reads.
# Set UNPACK=0 to measure the mounted case deliberately.
CONTAINER="${CONTAINER:-dtOO-diag}"
if [[ "${UNPACK:-1}" == "1" ]]; then
    export ENROOT_DATA_PATH="${TMPDIR:-/tmp}/diag-enroot-data"
    mkdir -p "$ENROOT_DATA_PATH"
    if [[ ! -d "$ENROOT_DATA_PATH/$CONTAINER" ]]; then
        echo "=== unpacking image (once, a few minutes)"
        time enroot create --name "$CONTAINER" "$IMAGE" || exit 1
    fi
    TARGET="$CONTAINER"
    echo "=== using unpacked container: $ENROOT_DATA_PATH/$CONTAINER"
else
    TARGET="$IMAGE"
    echo "=== using mounted image (squashfuse): $IMAGE"
fi

LOG="${LOG:-$WORK/build.log}"
TIMEOUT="${TIMEOUT:-1800}"

echo "=== log:     $LOG"
echo "=== watch:   tail -f $LOG"
echo "=== timeout: ${TIMEOUT}s, Ctrl-C works"
echo "=== the two dtOO phases run directly and unbuffered, with a timestamp"
echo "=== after each: env ready, state written, CreateStates, CreateMeshes."

echo "=== step 1: container start + sourcing only (should be seconds)"
time timeout 600 enroot start --root \
    -m "$WORK:$WORK" \
    "$TARGET" \
    bash -c "source /usr/lib/openfoam/openfoam2606/etc/bashrc; source /dtOO-install/bin/env.sh; echo SOURCED-OK"
echo "=== step 1 exit: $?"

echo "=== step 2: the dtOO phases"
START=$(date +%s)
timeout "$TIMEOUT" enroot start --root \
    -m "$REPO:$REPO" \
    -m "$WORK:$WORK" \
    "$TARGET" \
    bash -c "cd $WORK; source /usr/lib/openfoam/openfoam2606/etc/bashrc; source /dtOO-install/bin/env.sh; date +'[t] %T env ready'; python3.13 -u -c \"import sys; sys.path.insert(0,'$REPO/turbine_runner'); import dtoo_cfd_build as b; b._write_state_xml('$STATE', {})\"; date +'[t] %T state written'; python3.13 -u -c \"import sys; sys.path.insert(0,'.'); from tistos_files.createStatesAndMeshes import *; createStatesAndMeshes().CreateStates('$STATE')\"; date +'[t] %T CreateStates done'; python3.13 -u -c \"import sys; sys.path.insert(0,'.'); from tistos_files.createStatesAndMeshes import *; createStatesAndMeshes().CreateMeshes('$STATE','tistos_ru_of')\"; date +'[t] %T CreateMeshes done'" \
    > "$LOG" 2>&1
STATUS=$?
ELAPSED=$(( $(date +%s) - START ))

if (( STATUS == 124 )); then
    echo "=== TIMED OUT after ${ELAPSED}s — the same wall the production run hit"
else
    echo "=== exited with $STATUS after ${ELAPSED}s"
fi

echo "=== progress markers from the log"
grep -E "^\[cfd\]" "$LOG" || tail -20 "$LOG"
echo "=== when each artifact appeared (the CreateStates/CreateMeshes split)"
ls -lt --time-style=+%T "$WORK" | head

echo "=== what was produced"
du -sh "$WORK"/* 2>/dev/null | sort -rh | head
