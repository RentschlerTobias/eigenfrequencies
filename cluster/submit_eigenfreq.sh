#!/usr/bin/env bash
# SLURM submit script for eigenfrequencies optimisation on bwUniCluster 3.0.
#
# Usage:
#   EVAL_MODE=resonance_only bash cluster/submit_eigenfreq.sh
#   EVAL_MODE=cfd_only        bash cluster/submit_eigenfreq.sh
#   EVAL_MODE=combined        bash cluster/submit_eigenfreq.sh
#
# Or submit directly:
#   sbatch cluster/submit_eigenfreq.sh
#
# Key env vars (override via environment before sbatch):
#   EVAL_MODE       resonance_only | cfd_only | combined  (default: resonance_only)
#   OPTIMIZER       de | pso | cmaes | bo                 (default: de)
#   CONFIG_YAML     path to YAML config                   (default: examples/configs/tistos.yaml)
#   N_NODES         number of nodes                       (default: 2)
#   N_TASKS_NODE    tasks per node = workers per node     (default: 4)
#   WALLTIME        job wall time                         (default: 00:30:00 for dev, 24:00:00 for full)
#   PARTITION       SLURM partition                       (default: dev)
#   REPO            repo root on cluster filesystem
#   DE_STATE_FILE   checkpoint JSON path
#   DE_HISTORY_FILE history JSONL path

#SBATCH --job-name=eigenfreq
#SBATCH --partition=dev
#SBATCH --nodes=2
#SBATCH --ntasks-per-node=4
#SBATCH --cpus-per-task=1
#SBATCH --mem-per-cpu=4000
#SBATCH --time=00:30:00
#SBATCH --output=run_log/eigenfreq_%j.out

set -euo pipefail

# ── Defaults ────────────────────────────────────────────────────────────────
EVAL_MODE="${EVAL_MODE:-resonance_only}"
OPTIMIZER="${OPTIMIZER:-de}"
N_NODES="${SLURM_NNODES:-2}"
N_TASKS_NODE="${SLURM_NTASKS_PER_NODE:-4}"
N_WORKERS=$(( N_NODES * N_TASKS_NODE ))

REPO="${REPO:-/pfs/work9/workspace/scratch/st_ac136362-eigenfreq/eigenfrequencies}"
CONFIG_YAML="${CONFIG_YAML:-${REPO}/examples/configs/tistos.yaml}"

SCRATCH="${TMPDIR:-/scratch/slurm_tmpdir/job_${SLURM_JOB_ID}}"
RUN_DIR="${REPO}/runs/${EVAL_MODE}_${SLURM_JOB_ID}"
mkdir -p "${RUN_DIR}"

DE_URI_DIR="${RUN_DIR}/uris"
DE_STATE_FILE="${DE_STATE_FILE:-${RUN_DIR}/de_state.json}"
DE_HISTORY_FILE="${DE_HISTORY_FILE:-${RUN_DIR}/de_history.jsonl}"
mkdir -p "${DE_URI_DIR}"

export EIGENFREQUENCIES_REPO="${REPO}"
export EVAL_MODE
export DE_URI_DIR
export CFD_CASE_DIR="${SCRATCH}/cfd"
export TMPDIR="${SCRATCH}"

# ── Activate Python environment ──────────────────────────────────────────────
source ~/pe
source "${REPO}/.venv/bin/activate" 2>/dev/null || true

echo "========================================"
echo "[eigenfreq] EVAL_MODE=${EVAL_MODE}"
echo "[eigenfreq] OPTIMIZER=${OPTIMIZER}"
echo "[eigenfreq] N_WORKERS=${N_WORKERS}  (${N_NODES} nodes x ${N_TASKS_NODE} tasks)"
echo "[eigenfreq] RUN_DIR=${RUN_DIR}"
echo "[eigenfreq] CONFIG=${CONFIG_YAML}"
echo "[eigenfreq] JOB_ID=${SLURM_JOB_ID}"
echo "========================================"

# ── Start workers ────────────────────────────────────────────────────────────
# One srun task per worker — all in background.
for (( i=0; i<N_WORKERS; i++ )); do
    srun -n1 --exclusive \
        eigenfrequencies cluster worker "${i}" \
            --uri-dir "${DE_URI_DIR}" \
            --config "${CONFIG_YAML}" \
        > "${RUN_DIR}/worker_${i}.log" 2>&1 &
done

echo "[eigenfreq] Launched ${N_WORKERS} workers — waiting for URI files..."

# ── Run coordinator ──────────────────────────────────────────────────────────
RESUME_ARGS=""
if [[ -f "${DE_STATE_FILE}" ]]; then
    echo "[eigenfreq] Resuming from checkpoint: ${DE_STATE_FILE}"
    RESUME_ARGS="--resume ${DE_STATE_FILE}"
fi

eigenfrequencies optimize \
    --config "${CONFIG_YAML}" \
    --optimizer "${OPTIMIZER}" \
    --evaluator pyro5 \
    --uri-dir "${DE_URI_DIR}" \
    --workers "${N_WORKERS}" \
    --out "${RUN_DIR}" \
    ${RESUME_ARGS}

echo "[eigenfreq] Done. Results in ${RUN_DIR}"
