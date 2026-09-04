#!/usr/bin/env bash
# Probe: what do PATH and LD_LIBRARY_PATH look like after each setup step, and
# do they survive into the shell that actually runs the solve script?
#
#     bash cluster/probe_container_env.sh
#
# Run it on a compute node with the dtOO container unpacked
# (`source cluster/interactive_setup.sh` does that).
#
# Background: the cfd build succeeds, the solve dies with exit 127 and an empty
# log, and the OpenFOAM case holds a single line —
#
#     checkMesh: error while loading shared libraries: libfiniteVolume.so
#
# So checkMesh is on PATH but its libraries are not on LD_LIBRARY_PATH. The two
# setup lines run in order, OpenFOAM first and dtOO second; if the dtOO env.sh
# assigns LD_LIBRARY_PATH instead of appending to it, OpenFOAM's entries are
# gone by the time anything runs. The output below shows exactly where an entry
# disappears, and whether `exec sh` (how physics.py invokes the solve script)
# carries the variables at all.

CONTAINER="${CONTAINER:-dtOO}"
FOAM="${FOAM:-/usr/lib/openfoam/openfoam2606/etc/bashrc}"
DTOO_ENV="${DTOO_ENV:-/dtOO-install/bin/env.sh}"

if ! enroot list 2>/dev/null | grep -qx "$CONTAINER"; then
    echo "no container '$CONTAINER' in ${ENROOT_DATA_PATH:-<default>}" >&2
    echo "run: source cluster/interactive_setup.sh" >&2
    exit 1
fi

# One container start, everything reported from inside it. `exec` on the last
# statement: sourcing the OpenFOAM bashrc otherwise makes the shell replay its
# whole command string a second time.
enroot start --root "$CONTAINER" bash -c '
    show() { printf "\n=== %s\n  PATH entries with openfoam: %s\n  LD_LIBRARY_PATH: %s\n" \
        "$1" "$(echo "$PATH" | tr ":" "\n" | grep -c openfoam)" "${LD_LIBRARY_PATH:-<unset>}"; }

    show "before any setup"
    . '"$FOAM"'
    show "after the OpenFOAM bashrc"
    . '"$DTOO_ENV"'
    show "after the dtOO env.sh"

    printf "\n=== inside sh, which is what runs the solve script\n"
    sh -c "printf \"  LD_LIBRARY_PATH: %s\n\" \"\${LD_LIBRARY_PATH:-<unset>}\""
    sh -c "command -v checkMesh || echo \"  checkMesh NOT on PATH\""

    printf "\n=== can checkMesh actually load?\n"
    sh -c "checkMesh -help >/dev/null 2>&1 && echo \"  checkMesh runs\" || echo \"  checkMesh fails: $(checkMesh -help 2>&1 | head -1)\""

    printf "\n=== where libfiniteVolume.so actually lives\n"
    find / -name "libfiniteVolume.so" -maxdepth 6 2>/dev/null | head -3

    exec true
'
