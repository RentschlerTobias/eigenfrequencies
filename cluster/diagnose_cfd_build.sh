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
# alone exceeds 1800 s. The timings printed below say which part accounts for it.

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
echo "=== staging case inputs"
time cp -r "$REPO"/turbine_runner/cfd/{tistos_files,xml,boundaryData_RU_INLET} .

# Empty design = the template geometry, which is what candidate "baseline" uses.
echo '{}' > design.json

echo "=== container start + dtOO build (live output)"
time enroot start --root \
    -m "$REPO:$REPO" \
    -m "$WORK:$WORK" \
    "$IMAGE" \
    bash -c "
        cd $WORK
        echo '--- sourcing environments'
        time { source /usr/lib/openfoam/openfoam2606/etc/bashrc; source /dtOO-install/bin/env.sh; }
        echo '--- dtoo_cfd_build.py'
        time python3.13 $REPO/turbine_runner/dtoo_cfd_build.py design.json $STATE tistos_ru_of
    "

echo "=== what was produced"
ls -la "$WORK"
du -sh "$WORK"/* 2>/dev/null | sort -rh | head
