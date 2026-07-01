#!/bin/bash
# SLURM driver for quick DE smoke tests on bwUniCluster 3.0 dev partition.
#
# Submit with:  sbatch cluster/submit_dev.sh
#
#SBATCH --job-name=runner_de_smoke
#SBATCH --output=runner_de_smoke.out
#SBATCH --time=00:30:00
#SBATCH --nodes=1
#SBATCH --ntasks=4
#SBATCH --cpus-per-task=1
#SBATCH --partition=dev_cpu

set -euo pipefail

# --- environment -----------------------------------------------------------
source ~/pe
export LD_LIBRARY_PATH=~/dtOO/install/lib:~/dtOO/install/lib64:$LD_LIBRARY_PATH
export OSLO_LOCK_PATH=/tmp
export FOAM_SIGFPE=0

# FEniCSx/dolfinx runs via enroot:
export FENICSX_CONTAINER=${FENICSX_CONTAINER:-pyxis_fenicsx}

# --- run -------------------------------------------------------------------
cd "$SLURM_SUBMIT_DIR/turbine_runner"

# Smoke test: tiny population, few generations, no CFD
DE_POP_SIZE=${DE_POP_SIZE:-4} \
DE_MUTATION=${DE_MUTATION:-0.8} \
DE_CROSSOVER=${DE_CROSSOVER:-0.9} \
DE_MAX_GEN=${DE_MAX_GEN:-3} \
DE_TOL=${DE_TOL:-0.01} \
DE_SEED=${DE_SEED:-42} \
OPT_FMIN=${OPT_FMIN:-100} OPT_FMAX=${OPT_FMAX:-150} \
CFD_CASE_DIR="" \
  python3 optimize_de.py > optimize_de_smoke.log 2>&1
