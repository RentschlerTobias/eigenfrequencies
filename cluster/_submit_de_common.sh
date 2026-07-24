#!/bin/bash
# Shared in-allocation body for the DE submit variants. NOT passed to sbatch
# directly — sourced from variant wrappers (submit_de_cfd_only.sh,
# submit_de_combined.sh, submit_de.sh) that carry the #SBATCH header.
# The variant must set BEFORE sourcing:
#   RUN_TAG        short id; namespaces state/history/log/uri dirs
#   EVAL_MODE      combined | cfd_only | resonance_only
# Optional (defaults shown):
#   W_RESONANCE    resonance weight            (default: 1.0)
#   DE_POP_SIZE    population                  (default: SLURM_NNODES * SLURM_NTASKS_PER_NODE)
#   DE_MAX_GEN     generations                 (default: 10)
#   DE_SEED        RNG seed                    (default: 42)
#   CFD_ENABLED    1 = run CFD evals           (default: 1)
#   CFD_CASE_DIR   OpenFOAM case parent        (default: $TMPDIR)

set -euo pipefail

RUN_TAG="${RUN_TAG:?RUN_TAG must be set by the variant wrapper}"
EVAL_MODE="${EVAL_MODE:?EVAL_MODE must be set by the variant wrapper}"

# vendor env tolerates unset vars + nonzero trailing exit (OpenFOAM bashrc)
set +u
source ~/pe || true
set -u

# CRITICAL: $0 is rewritten by SLURM to /var/spool/slurmd/jobXXXX/slurm_script,
# so use $SLURM_SUBMIT_DIR instead of computing from $0.
REPO_ROOT="${SLURM_SUBMIT_DIR:-$PWD}"
cd "$REPO_ROOT"

POP_SIZE="${DE_POP_SIZE:-$((SLURM_NNODES * SLURM_NTASKS_PER_NODE))}"
MAX_GEN="${DE_MAX_GEN:-10}"
SEED="${DE_SEED:-42}"

export CFD_CASE_DIR="${CFD_CASE_DIR:-$TMPDIR}"
export DE_POP_SIZE="$POP_SIZE"
export DE_MAX_GEN="$MAX_GEN"
export DE_SEED="$SEED"
export EVAL_MODE="$EVAL_MODE"
export W_RESONANCE="${W_RESONANCE:-1.0}"
export CFD_ENABLED="${CFD_ENABLED:-1}"
export DESIGN_PRESET="${DESIGN_PRESET:-full30}"
# dtOO + OpenFOAM stack (from de_framework start_server.sh): avoid FPE aborts in
# simpleFoam and give OSLO a writable lock dir.
export FOAM_SIGFPE="${FOAM_SIGFPE:-0}"
export OSLO_LOCK_PATH="${OSLO_LOCK_PATH:-/tmp}"

# Per-variant namespace: two concurrent runs never clobber each other's
# checkpoints, histories, URIs or worker logs.
LOG_DIR="$REPO_ROOT/server_logs/${RUN_TAG}"
rm -rf "$LOG_DIR"
mkdir -p "$LOG_DIR"
export DE_URI_DIR="$LOG_DIR/uris"
mkdir -p "$DE_URI_DIR"
# Pre-set DE_STATE_FILE/DE_HISTORY_FILE win (e.g. to resume an old checkpoint).
export DE_STATE_FILE="${DE_STATE_FILE:-$REPO_ROOT/turbine_runner/de_state_${RUN_TAG}.json}"
export DE_HISTORY_FILE="${DE_HISTORY_FILE:-$REPO_ROOT/turbine_runner/de_history_${RUN_TAG}.jsonl}"

echo "========================================"
echo "[DE] variant=$RUN_TAG eval_mode=$EVAL_MODE on $(hostname)"
echo "[DE] POP_SIZE=$POP_SIZE  MAX_GEN=$MAX_GEN  SEED=$SEED"
echo "[DE] W_RESONANCE=$W_RESONANCE  CFD_ENABLED=$CFD_ENABLED"
echo "[DE] SLURM: $SLURM_NNODES nodes x $SLURM_NTASKS_PER_NODE tasks/node, job $SLURM_JOB_ID"
echo "[DE] state=$DE_STATE_FILE"
echo "[DE] history=$DE_HISTORY_FILE"
echo "[DE] CFD_CASE_DIR=$CFD_CASE_DIR"
echo "========================================"

# ── Copy shared data to local NVMe on all nodes ──
srun -N "$SLURM_NNODES" -n "$SLURM_NNODES" \
    cp -r "$REPO_ROOT/turbine_runner/data" "$TMPDIR/" 2>/dev/null || true

# ── Start workers via srun (one task per worker, distributed across nodes) ──
echo "[DE] Starting $POP_SIZE workers via srun (distributed across $SLURM_NNODES nodes)..."
for i in $(seq 0 $((POP_SIZE-1))); do
    srun -n 1 -N 1 python3 -u turbine_runner/server_de.py "$i" \
        > "$LOG_DIR/worker_${i}.log" 2>&1 &
done

# ── Run DE client — polls DE_URI_DIR until all POP_SIZE workers appear ──
echo "[DE] Running DE client..."
python3 -u turbine_runner/optimize_de.py

echo "[DE] Done. Logs: $LOG_DIR"
# Workers are backgrounded srun steps; they terminate when this job ends.
# NOTE: no scancel $SLURM_JOB_ID here — that would mark this job CANCELLED.
