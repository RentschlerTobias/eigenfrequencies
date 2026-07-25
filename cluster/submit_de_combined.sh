#!/bin/bash
#SBATCH --job-name=de_combined
#SBATCH --output=de_combined_%j.out
#SBATCH --time=08:00:00
#SBATCH --nodes=16
#SBATCH --ntasks-per-node=4
#SBATCH --cpus-per-task=16
#SBATCH --hint=nomultithread
#SBATCH --partition=cpu_il

# Combined DE variant (EVAL_MODE=combined): workers run dtoo + FEniCSx modal +
# CFD, objective = cfd_scalar + W_RESONANCE * resonance_term (BPF-harmonic
# avoidance). Defaults above are production (16 nodes x 4 workers x 16 cores,
# POP_SIZE=64 derived from nodes x tasks, MAX_GEN=50, ~4-5h on cpu_il).
#
# Smoke override (dev_cpu_il, 30 min, quick pipeline check):
#   sbatch --partition=dev_cpu_il --nodes=8 --time=00:30:00 \
#          --export=ALL,DE_MAX_GEN=1 cluster/submit_de_combined.sh
# Checkpoint/resume via turbine_runner/de_state_combined.json.

set -euo pipefail

export RUN_TAG="combined"
export EVAL_MODE="combined"
export W_RESONANCE="${W_RESONANCE:-0.5}"
export DE_MAX_GEN="${DE_MAX_GEN:-50}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# $BASH_SOURCE resolves to the spooled copy under SLURM; cluster/ sits next to it
# only in the submit dir, so prefer SLURM_SUBMIT_DIR when inside an allocation.
COMMON_DIR="${SLURM_SUBMIT_DIR:-$SCRIPT_DIR}/cluster"
source "$COMMON_DIR/_submit_de_common.sh"
