#!/usr/bin/env bash
#SBATCH --job-name=fenicsx_enroot_smoke
#SBATCH --output=fenicsx_enroot_smoke_%j.out
#SBATCH --time=00:10:00
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --cpus-per-task=4
#SBATCH --partition=dev_cpu_il

# Smoke test: verify the modal stage runs inside the FEniCSx enroot container
# on bwUniCluster 3.0. Counterpart to submit_dtoo_enroot_smoke.sh.
#
# This goes one step further than the dtOO smoke test: it does not only import
# the libraries, it solves. The fixture mesh in tests/fixtures/ is a coarse
# unit box — a few hundred DOFs, seconds — so a green run means the whole
# chain works: gmsh reads the mesh, dolfinx builds the space, the eigensolver
# returns frequencies.

set -euo pipefail

ENROOT_IMAGE="${ENROOT_IMAGE:-${WS:-$HOME}/enroot-images/dolfinx.sqsh}"
# The stock dolfinx image has no gmsh; a pip --target directory supplies it.
# Leave empty when using the self-contained image built from the Dockerfile.
PYLIBS="${PYLIBS:-$HOME/pylibs}"
REPO="${EIGENFREQUENCIES_REPO:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"

echo "========================================"
echo "[fenicsx-enroot-smoke] host=$(hostname)"
echo "[fenicsx-enroot-smoke] image=$ENROOT_IMAGE"
echo "[fenicsx-enroot-smoke] repo=$REPO"
echo "[fenicsx-enroot-smoke] job=${SLURM_JOB_ID:-none}"
echo "========================================"

if [[ ! -f "$ENROOT_IMAGE" ]]; then
    echo "[fenicsx-enroot-smoke] ERROR: enroot image not found: $ENROOT_IMAGE"
    echo "[fenicsx-enroot-smoke] Run the import steps in cluster/enroot_fenicsx_import.md first."
    exit 1
fi

SPEC="${TMPDIR:-/tmp}/modal_smoke_spec.json"
cat > "$SPEC" <<EOF
{
  "msh_path": "$REPO/tests/fixtures/unit_box_coarse.msh",
  "bc": {"mode": "axial_plane", "axis": "z", "plane_value": 0.0, "plane_tol": 1e-6},
  "solver": {"num_eigenvalues": 5, "element_degree": 2, "solver_backend": "scipy"}
}
EOF
echo "[fenicsx-enroot-smoke] spec: $SPEC"

# The repository and the spec are mounted at their own paths, exactly as
# eigenfrequencies.hydroflow.physics does it, so the paths inside the spec
# resolve unchanged in the container.
# HOME/TMPDIR/XDG_RUNTIME_DIR point at /tmp because PMIx otherwise falls back
# to /run/user/$UID, which is unwritable in a batch allocation.
srun -n1 -N1 enroot start --root \
    --mount "$REPO:$REPO" \
    --mount "$(dirname "$SPEC"):$(dirname "$SPEC")" \
    ${PYLIBS:+--mount "$PYLIBS:$PYLIBS"} \
    "$ENROOT_IMAGE" \
    bash -c "
        set -euo pipefail
        export HOME=/tmp DOLFINX_CACHE_DIR=/tmp XDG_RUNTIME_DIR=/tmp TMPDIR=/tmp
        # Appended, not assigned: the image keeps its own dolfinx on PYTHONPATH.
        [ -n "$PYLIBS" ] && export PYTHONPATH="$PYLIBS:\$PYTHONPATH"
        echo '[container] starting on \$(hostname)'
        python3 $REPO/src/eigenfrequencies/hydroflow/physics.py modal $SPEC
        echo '[container] EXIT=0'
    "

EXIT_CODE=$?
echo "[fenicsx-enroot-smoke] container exit code: $EXIT_CODE"
echo "[fenicsx-enroot-smoke] a green run prints a RESULT_JSON line with 5 frequencies"
exit $EXIT_CODE
