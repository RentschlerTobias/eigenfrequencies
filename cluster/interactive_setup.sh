#!/usr/bin/env bash
# Per-allocation setup for interactive work on a compute node. Source it, do
# not execute it:
#
#     source cluster/interactive_setup.sh
#
# Every allocation gets a fresh $TMPDIR, and `enroot create` puts the unpacked
# containers inside it — so none of this survives the job. It has to run again
# in every new allocation, and again in every new shell on the node (a second
# window opened with `srun --jobid=<id> --overlap --pty bash` starts empty too).
# Losing $W or $ENROOT_DATA_PATH halfway through a debugging session produces
# `-m ":"` and a `cd` to $HOME, which look like container bugs and are not.
#
# Idempotent: re-sourcing neither re-unpacks an existing container nor
# overwrites already staged case inputs.

if [ -z "${TMPDIR:-}" ]; then
    echo "interactive_setup: no TMPDIR — are you on a compute node?" >&2
    echo "interactive_setup:   salloc -p dev_cpu_il -N1 --exclusive -t 00:30:00" >&2
    return 1 2>/dev/null || exit 1
fi

# WS, ENROOT_IMAGES, the zstd guard and the python module.
# shellcheck source=/dev/null
. "$(dirname "${BASH_SOURCE[0]}")/cluster_env.sh"

# Node-local, exactly where submit_hydroflow_opt.sh puts it, so an interactive
# session and a batch job see the same container names.
export ENROOT_DATA_PATH="$TMPDIR/enroot-data"
mkdir -p "$ENROOT_DATA_PATH"

for name in dtOO dolfinx; do
    image="$ENROOT_IMAGES/$name.sqsh"
    [ -f "$image" ] || { echo "interactive_setup: no $image — skipping $name" >&2; continue; }
    if enroot list 2>/dev/null | grep -qx "$name"; then
        echo "interactive_setup: $name already unpacked"
    else
        echo "interactive_setup: unpacking $name (~8 s)"
        enroot create --name "$name" "$image" || \
            echo "interactive_setup: enroot create failed for $name" >&2
    fi
done

# A scratch case directory with the CFD inputs staged the way physics.py stages
# them, for hand-run container commands.
export W="${W:-$TMPDIR/cdtest}"
mkdir -p "$W"
for sub in tistos_files xml boundaryData_RU_INLET; do
    [ -d "$W/$sub" ] || cp -r "$EIGENFREQUENCIES_REPO/turbine_runner/cfd/$sub" "$W/" 2>/dev/null
done

export R="$EIGENFREQUENCIES_REPO"

echo "interactive_setup: WS=$WS"
echo "interactive_setup: R=$R"
echo "interactive_setup: W=$W"
echo "interactive_setup: ENROOT_DATA_PATH=$ENROOT_DATA_PATH"
echo "interactive_setup: containers: $(enroot list 2>/dev/null | tr '\n' ' ')"
