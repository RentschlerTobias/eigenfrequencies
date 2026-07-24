#!/bin/bash
#SBATCH --job-name=de_combined
#SBATCH --output=de_combined_%j.out
#SBATCH --time=00:30:00
#SBATCH --nodes=6
#SBATCH --ntasks-per-node=4
#SBATCH --cpus-per-task=16
#SBATCH --hint=nomultithread
#SBATCH --partition=dev_cpu_il

# Combined DE variant (EVAL_MODE=combined): workers run dtoo + FEniCSx modal +
# CFD, objective = cfd_scalar + W_RESONANCE * resonance_term (BPF-harmonic
# avoidance). Defaults above are the smoke test (6 nodes x 4 workers x 16 cores,
# POP_SIZE=24 derived from nodes x tasks, MAX_GEN=1).
#
# Production override at submission time, e.g.:
#   sbatch --partition=cpu_il --nodes=4 --ntasks-per-node=4 --cpus-per-task=16 \
#          --time=08:00:00 --export=ALL,DE_POP_SIZE=16,DE_MAX_GEN=20,W_RESONANCE=0.5 \
#          cluster/submit_de_combined.sh
# Checkpoint/resume via turbine_runner/de_state_combined.json.

set -euo pipefail

export RUN_TAG="combined"
export EVAL_MODE="combined"
export W_RESONANCE="${W_RESONANCE:-0.5}"
export DE_MAX_GEN="${DE_MAX_GEN:-1}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# $BASH_SOURCE resolves to the spooled copy under SLURM; cluster/ sits next to it
# only in the submit dir, so prefer SLURM_SUBMIT_DIR when inside an allocation.
COMMON_DIR="${SLURM_SUBMIT_DIR:-$SCRIPT_DIR}/cluster"
source "$COMMON_DIR/_submit_de_common.sh"
