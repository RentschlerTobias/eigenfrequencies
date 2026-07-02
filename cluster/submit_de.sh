#!/bin/bash
#SBATCH --job-name=de_opti
#SBATCH --output=de_opti_%j.out
#SBATCH --time=02:00:00
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=20
#SBATCH --cpus-per-task=1
#SBATCH --partition=cpu
#SBATCH --dependency=singleton

# Differential Evolution (DE) batch job — Pyro5 worker servers per core.
# Follows rl_framework/start.sh schema: srun per worker, Name Server on head node.

source ~/pe

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

POP_SIZE="${DE_POP_SIZE:-20}"
MAX_GEN="${DE_MAX_GEN:-30}"
SEED="${DE_SEED:-42}"
NS_HOST=$(hostname)

export PYRO_NS_HOST="$NS_HOST"
export CFD_CASE_DIR="${CFD_CASE_DIR:-}"
export DE_POP_SIZE="$POP_SIZE"
export DE_MAX_GEN="$MAX_GEN"
export DE_SEED="$SEED"

LOG_DIR="$REPO_ROOT/server_logs"
rm -rf "$LOG_DIR"
mkdir -p "$LOG_DIR"

echo "========================================"
echo "[DE] Pyro5 DE batch job on $NS_HOST"
echo "[DE] POP_SIZE=$POP_SIZE  MAX_GEN=$MAX_GEN  SEED=$SEED"
echo "[DE] CFD_CASE_DIR=$CFD_CASE_DIR"
echo "========================================"

# ── Start Name Server ──
echo "[DE] Starting Name Server..."
python3 -m Pyro5.nameserver -n "$NS_HOST" > "$LOG_DIR/nameserver.log" 2>&1 &
NS_PID=$!
sleep 3

# ── Start workers via srun (one task per worker) ──
echo "[DE] Starting $POP_SIZE workers via srun..."
for i in $(seq 0 $((POP_SIZE-1))); do
    srun -n 1 -N 1 python3 -u turbine_runner/server_de.py "$i" "$NS_HOST" > "$LOG_DIR/worker_${i}.log" 2>&1 &
done

sleep 2

# ── Run DE client ──
echo "[DE] Running DE client..."
python3 turbine_runner/optimize_de.py

echo "[DE] Done. Logs: $LOG_DIR"
echo "[DE] Kill Name Server: kill $NS_PID"
echo "[DE] Kill workers: scancel $SLURM_JOB_ID"
