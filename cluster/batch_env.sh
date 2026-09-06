#!/usr/bin/env bash
# Batch-safe environment shim for sbatch jobs. Source it, do not execute it:
#
#     source ~/eigenfrequencies/cluster/batch_env.sh
#
# Provisions WS, ENROOT_IMAGES, ENROOT_DATA_PATH and EIGENFREQUENCIES_REPO for
# non-interactive SLURM contexts. Differs from sourcing cluster_env.sh directly
# in that no ssh-agent is started (batch jobs have no agent to attach to) and
# ws_find is the last resort, never the silent default.

# Repo root = grandparent of this script (cluster/ -> repo). cd-in-subshell
# normalises relative BASH_SOURCE so the result is always absolute.
EIGENFREQUENCIES_REPO="${EIGENFREQUENCIES_REPO:-$(
    cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd
)}"

# Workspace resolution: prefer an explicit $WS (SLURM-injected by the wrapper),
# fall back to ws_find on the login node. cluster_env.sh has its own ws_find
# fallback, but we resolve here so the failure message is local and explicit
# rather than buried in a downstream default.
if [ -z "${WS:-}" ]; then
    if command -v ws_find >/dev/null 2>&1; then
        WS="$(ws_find "${WS_NAME:-eigenfreq}" 2>/dev/null || true)"
    fi
fi
if [ -z "${WS:-}" ]; then
    echo "batch_env: no workspace — export WS=/path/to/workspace or run ws_allocate ${WS_NAME:-eigenfreq} 60 on a login node" >&2
    return 1 2>/dev/null || exit 1
fi
export WS

# Source cluster_env.sh with WS pre-set so its own ws_find branch (lines 32-34)
# is skipped. ssh-agent startup is suppressed inside cluster_env.sh when
# SLURM_JOB_ID is set; the stub below keeps that contract on the dev machine
# during local QA.
SLURM_JOB_ID="${SLURM_JOB_ID:-qa}" \
    . "$(dirname "${BASH_SOURCE[0]}")/cluster_env.sh"

# Node-local enroot import scratch — the same path submit_hydroflow_opt.sh:202
# and interactive_setup.sh:29 use, so a batch job, an interactive srun session
# and the diagnostic tools see the same container names.
export ENROOT_DATA_PATH="${ENROOT_DATA_PATH:-${TMPDIR:-/tmp}/enroot-data}"
mkdir -p "$ENROOT_DATA_PATH"

# ENROOT_IMAGES is already exported by cluster_env.sh:56 as $WS/enroot-images;
# reaffirm here so callers can rely on a single import boundary.

echo "WS=$WS"
echo "ENROOT_IMAGES=$ENROOT_IMAGES"
echo "ENROOT_DATA_PATH=$ENROOT_DATA_PATH"
echo "EIGENFREQUENCIES_REPO=$EIGENFREQUENCIES_REPO"
