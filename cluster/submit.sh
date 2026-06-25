#!/bin/bash
# SLURM driver for the CFD + eigenfrequency runner optimization on bwUniCluster 3.0.
#
# Submit with:  sbatch cluster/submit.sh
#
#SBATCH --job-name=runner_cfd_eig
#SBATCH --output=runner_cfd_eig.out
#SBATCH --time=00:30:00
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --partition=dev_cpu

set -euo pipefail

# --- environment -----------------------------------------------------------
source ~/pe
export LD_LIBRARY_PATH=~/dtOO/install/lib:~/dtOO/install/lib64:$LD_LIBRARY_PATH
export OSLO_LOCK_PATH=/tmp
export FOAM_SIGFPE=0

# FEniCSx/dolfinx runs via enroot (imported from docker://dolfinx/dolfinx:stable):
export FENICSX_CONTAINER=${FENICSX_CONTAINER:-pyxis_fenicsx}

# --- run -------------------------------------------------------------------
cd "$SLURM_SUBMIT_DIR/turbine_runner"

OPT_MAX_ITER=${OPT_MAX_ITER:-40} \
OPT_FMIN=${OPT_FMIN:-100} OPT_FMAX=${OPT_FMAX:-150} \
CFD_CASE_DIR=${CFD_CASE_DIR:-""} \
  python3 optimize_multi.py > optimize_multi.log 2>&1
