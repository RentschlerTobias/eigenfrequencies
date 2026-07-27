#!/bin/bash
#SBATCH --job-name=de_resonance_only
#SBATCH --output=de_resonance_only_%j.out
#SBATCH --time=24:00:00
#SBATCH --nodes=4
#SBATCH --ntasks-per-node=4
#SBATCH --cpus-per-task=16
#SBATCH --hint=nomultithread
#SBATCH --partition=cpu_il

# Modal-only DE variant (EVAL_MODE=resonance_only): workers run dtoo build +
# FEniCSx modal analysis only — no OpenFOAM CFD. Objective = resonance_term
# (BPF-harmonic avoidance penalty). CFD_ENABLED=0 short-circuits the CFD branch
# in server_de.py so simpleFoam never starts.
#
# Defaults match submit_de_combined.sh / submit_de_cfd_only.sh so all three
# runs are directly comparable. Low-node / long-walltime config: 4 nodes x 4
# workers x 16 cores, POP_SIZE=16, MAX_GEN=100, 24h walltime
# (~3-5h expected, no CFD).
#
# Smoke override (dev_cpu_il, 30 min, quick pipeline check):
#   sbatch --partition=dev_cpu_il --nodes=8 --time=00:30:00 \
#          --export=ALL,DE_MAX_GEN=1 cluster/submit_de_resonance_only.sh
# Checkpoint/resume via turbine_runner/de_state_resonance_only.json.

set -euo pipefail

export RUN_TAG="resonance_only"
export EVAL_MODE="resonance_only"
export W_RESONANCE="${W_RESONANCE:-1.0}"
export CFD_ENABLED="${CFD_ENABLED:-0}"
export DE_MAX_GEN="${DE_MAX_GEN:-100}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# $BASH_SOURCE resolves to the spooled copy under SLURM; cluster/ sits next to it
# only in the submit dir, so prefer SLURM_SUBMIT_DIR when inside an allocation.
COMMON_DIR="${SLURM_SUBMIT_DIR:-$SCRIPT_DIR}/cluster"
source "$COMMON_DIR/_submit_de_common.sh"