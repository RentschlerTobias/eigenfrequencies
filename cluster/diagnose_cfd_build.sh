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
# The in-container script is written to a file rather than passed as a quoted
# string. Two levels of quoting around a multi-line body is how the first
# version of this ended up echoing its own first line several hundred times.

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

cat > "$WORK/inner.sh" <<INNER
cd "$WORK"
echo "[t] \$(date +%T) container up"
source /usr/lib/openfoam/openfoam2606/etc/bashrc
source /dtOO-install/bin/env.sh
echo "[t] \$(date +%T) environments sourced"
python3.13 "$REPO/turbine_runner/dtoo_cfd_build.py" design.json "$STATE" tistos_ru_of
echo "[t] \$(date +%T) build finished with status \$?"
INNER

# A heartbeat while it runs. dtOO is silent for minutes at a time, and silence
# is indistinguishable from a hang — which is exactly the question here.
HEARTBEAT="${HEARTBEAT:-30}"

echo "=== dtOO build (live). dtoo_cfd_build.py prints CreateStates and"
echo "=== CreateMeshes separately, so the gap between those lines is the split."
echo "=== heartbeat every ${HEARTBEAT}s; set HEARTBEAT=0 to silence it."

START=$(date +%s)
enroot start --root \
    -m "$REPO:$REPO" \
    -m "$WORK:$WORK" \
    "$IMAGE" \
    bash "$WORK/inner.sh" &
BUILD_PID=$!

if [[ "$HEARTBEAT" != "0" ]]; then
    while kill -0 "$BUILD_PID" 2>/dev/null; do
        sleep "$HEARTBEAT"
        kill -0 "$BUILD_PID" 2>/dev/null || break
        ELAPSED=$(( $(date +%s) - START ))
        # What exists so far says more than the elapsed time alone: the case
        # directory appears once CreateMeshes starts writing.
        LATEST=$(ls -t "$WORK" 2>/dev/null | head -3 | tr '\n' ' ')
        echo "[t] $(date +%T) ${ELAPSED}s elapsed, newest in work dir: $LATEST"
    done
fi

wait "$BUILD_PID"
STATUS=$?
echo "=== build exited with $STATUS after $(( $(date +%s) - START ))s"

echo "=== what was produced"
du -sh "$WORK"/* 2>/dev/null | sort -rh | head
