#!/usr/bin/env bash
#SBATCH --job-name=dtOO_enroot_smoke
#SBATCH --output=dtOO_enroot_smoke_%j.out
#SBATCH --time=00:05:00
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --cpus-per-task=1
#SBATCH --partition=dev_cpu_il

# Smoke test: verify dtOO SWIG bindings load inside an enroot container
# on bwUniCluster 3.0. See cluster/enroot_dtoo_import.md for setup.

set -euo pipefail

ENROOT_IMAGE="${ENROOT_IMAGE:-$HOME/enroot-images/dtOO-opensuse.sqsh}"

echo "========================================"
echo "[dtOO-enroot-smoke] host=$(hostname)"
echo "[dtOO-enroot-smoke] image=$ENROOT_IMAGE"
echo "[dtOO-enroot-smoke] job=$SLURM_JOB_ID"
echo "========================================"

if [[ ! -f "$ENROOT_IMAGE" ]]; then
    echo "[dtOO-enroot-smoke] ERROR: enroot image not found: $ENROOT_IMAGE"
    echo "[dtOO-enroot-smoke] Run the import steps in cluster/enroot_dtoo_import.md first."
    exit 1
fi

# Run the import test inside the container.
# Both environment files must be sourced before python3.13, otherwise shared
# libraries (libPstream.so, libTKFeat.so.7.9) are not found.
srun -n1 -N1 enroot start --root "$ENROOT_IMAGE" bash -c '
    set -euo pipefail
    echo "[container] starting on $(hostname)"
    source /usr/lib/openfoam/openfoam2606/etc/bashrc
    source /dtOO-install/bin/env.sh
    python3.13 -c "import dtOOPythonSWIG; print(\"dtOOPythonSWIG imported ok\")"
    echo "[container] EXIT=0"
'

EXIT_CODE=$?
echo "[dtOO-enroot-smoke] container exit code: $EXIT_CODE"
exit $EXIT_CODE
