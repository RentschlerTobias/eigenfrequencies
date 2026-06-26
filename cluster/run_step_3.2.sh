#!/bin/bash
#SBATCH --job-name=runner_eval
#SBATCH --output=runner_eval.out
#SBATCH --time=00:10:00
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --partition=dev_cpu

set -euo pipefail

REPO=/home/st/st_us-042020/st_ac136362/eigen/eigenfrequencies

enroot start -m "$REPO:/workspace" pyxis_fenicsx \
    python3 /workspace/turbine_runner/evaluate.py \
    /workspace/turbine_runner/data/runner.msh
