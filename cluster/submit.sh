#!/bin/bash
# SLURM driver for the CFD + eigenfrequency runner optimization on bwUniCluster 3.0.
#
# Patterned on the de_framework reference start.sh (partition dev_cpu_il, $TMPDIR
# staging, one worker per task). Adapt the workspace paths and the per-design
# launch to the eigenfrequencies optimize_multi.py loop.
#
# Submit with:  sbatch cluster/submit.sh
#
#SBATCH --job-name=runner_cfd_eig
#SBATCH --output=runner_cfd_eig.out
#SBATCH --time=00:30:00
#SBATCH --nodes=4
#SBATCH --ntasks-per-node=8
#SBATCH --cpus-per-task=16
#SBATCH --partition=dev_cpu_il
#SBATCH --exclusive

set -euo pipefail

# --- environment -----------------------------------------------------------
# dtOO + OpenFOAM (for geometry build + simpleFoam CFD objectives):
source ~/de                      # de_framework env file; or: module load ...
# . dtoo of_v2406_15.6           # dtOO + OpenFOAM v2406 module (reference)
export OSLO_LOCK_PATH=/tmp
export FOAM_SIGFPE=0

# FEniCSx/dolfinx for the modal solve is NOT in the dtOO env. It runs via the
# apptainer image built from cluster/apptainer_fenicsx.def:
export FENICSX_SIF=${FENICSX_SIF:-$HOME/images/eigenfrequencies-fenicsx.sif}

# --- stage inputs to node-local $TMPDIR ------------------------------------
WS=${WS:-$PWD}
srun -N "$SLURM_NNODES" -n "$SLURM_NNODES" cp -r "$WS/turbine_runner" "$TMPDIR"
srun -N "$SLURM_NNODES" -n "$SLURM_NNODES" cp -r "$WS/cluster" "$TMPDIR"
# stage the dtOO case dir (machine.xml, xml/, tistos_files/) here as well:
# srun ... cp -r "$WS/tistos_files" "$TMPDIR"

cd "$TMPDIR/turbine_runner"

# --- run the optimization --------------------------------------------------
# The modal solve inside optimize_multi.py is dispatched via apptainer; see
# cluster/env_notes.md for wiring FENICSX_IMAGE -> apptainer exec.
OPT_MAX_ITER=${OPT_MAX_ITER:-40} \
OPT_FMIN=${OPT_FMIN:-100} OPT_FMAX=${OPT_FMAX:-150} \
CFD_CASE_DIR=${CFD_CASE_DIR:-$TMPDIR/turbine_runner/data/of_case} \
  python3 optimize_multi.py > optimize_multi.log 2>&1
