#!/bin/bash
#SBATCH --job-name=runner_eval
#SBATCH --output=runner_eval_%j.out
#SBATCH --time=00:10:00
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --partition=dev_cpu

set -euo pipefail

# Host-Pfad (von dir bestätigt)
REPO=/home/st/st_us-042020/st_ac136362/eigen/eigenfrequencies

# Cache/Home ins Container-Tmp schreiben, damit nichts auf den Host-Home (ro) schreibt
enroot start -m "$REPO:/workspace" pyxis_fenicsx \
    bash -c 'export HOME=/tmp; export DOLFINX_CACHE_DIR=/tmp; python3 /workspace/turbine_runner/evaluate.py /workspace/turbine_runner/data/runner.msh'
