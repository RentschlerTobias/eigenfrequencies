#!/bin/bash
#SBATCH --job-name=de_opti
#SBATCH --output=de_opti_%j.out
#SBATCH --time=00:30:00
#SBATCH --nodes=8
#SBATCH --ntasks-per-node=32
#SBATCH --cpus-per-task=2
#SBATCH --hint=nomultithread
#SBATCH --partition=dev_cpu_il
#SBATCH --dependency=singleton

# Legacy DE entry point — kept for backward compatibility. Prefer
# cluster/submit_de_cfd_only.sh or cluster/submit_de_combined.sh for new work;
# they namespace state/history/logs per variant and can run concurrently.
# This wrapper behaves like the old monolith: EVAL_MODE=combined,
# W_RESONANCE=1.0, POP_SIZE=nnodes*ntasks.
#
# CFD runs (CFD_ENABLED=1, default): each worker runs a full simpleFoam solve
# (~minutes), so use a production partition with real walltime and more cores
# per worker for the MPI solve, and fewer workers:
#   sbatch --partition=cpu_il --nodes=4 --ntasks-per-node=4 --cpus-per-task=16 \
#          --time=08:00:00 cluster/submit_de.sh
# Checkpoint/resume (turbine_runner/de_state_legacy.json) makes multi-hour
# runs safe to resubmit. Smoke-test the CFD wiring first: DE_POP_SIZE=4
# DE_MAX_GEN=1.

set -euo pipefail

export RUN_TAG="legacy"
export EVAL_MODE="combined"
export W_RESONANCE="${W_RESONANCE:-1.0}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMMON_DIR="${SLURM_SUBMIT_DIR:-$SCRIPT_DIR}/cluster"
source "$COMMON_DIR/_submit_de_common.sh"
