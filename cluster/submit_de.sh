#!/bin/bash
#SBATCH --job-name=de_opti
#SBATCH --output=de_opti_%j.out
#SBATCH --time=00:30:00
#SBATCH --nodes=8
#SBATCH --ntasks-per-node=8
#SBATCH --cpus-per-task=1
#SBATCH --hint=nomultithread
#SBATCH --partition=dev_cpu_il
#SBATCH --dependency=singleton

# Differential Evolution (DE) batch job — multi-node Pyro5 workers.
# Follows rl_framework/start.sh: srun per worker, Name Server on head node.
# Distributes workers across SLURM nodes to avoid per-node OOM
# (e.g. 64 workers on dev_cpu_il = 1 node x 256 GiB is too tight).
#
# Override at submission time:
#   sbatch --partition=cpu --nodes=4 --ntasks-per-node=16 \
#          --time=02:00:00 cluster/submit_de.sh

source ~/pe

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

POP_SIZE="${DE_POP_SIZE:-64}"
MAX_GEN="${DE_MAX_GEN:-4}"
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
echo "[DE] Pyro5 DE multi-node on $NS_HOST"
echo "[DE] POP_SIZE=$POP_SIZE  MAX_GEN=$MAX_GEN  SEED=$SEED"
echo "[DE] SLURM: $SLURM_NNODES nodes x $SLURM_NTASKS_PER_NODE tasks/node"
echo "[DE] Partition=${SLURM_JOB_PARTITION:-dev_cpu_il}"
echo "[DE] CFD_CASE_DIR=$CFD_CASE_DIR"
echo "========================================"

# ── Copy shared data to local NVMe on all nodes ──
srun -N "$SLURM_NNODES" -n "$SLURM_NNODES" \
    cp -r "$REPO_ROOT/turbine_runner/data" "$TMPDIR/" 2>/dev/null || true

# ── Start Name Server on head node ──
echo "[DE] Starting Name Server..."
python3 -m Pyro5.nameserver -n "$NS_HOST" > "$LOG_DIR/nameserver.log" 2>&1 &
NS_PID=$!
sleep 3

if ! ps -p $NS_PID > /dev/null; then
    echo "[DE] ERROR: Name Server failed to start!"
    cat "$LOG_DIR/nameserver.log"
    exit 1
fi

# ── Start workers via srun (one task per worker, distributed across nodes) ──
echo "[DE] Starting $POP_SIZE workers via srun (distributed across $SLURM_NNODES nodes)..."
for i in $(seq 0 $((POP_SIZE-1))); do
    srun -n 1 -N 1 python3 -u turbine_runner/server_de.py "$i" "$NS_HOST" \
        > "$LOG_DIR/worker_${i}.log" 2>&1 &
done

# ── Run DE client — waits for POP_SIZE workers via _discover_servers polling ──
echo "[DE] Running DE client (polls up to 120s for all $POP_SIZE workers)..."
python3 turbine_runner/optimize_de.py

# ── Cleanup ──
echo "[DE] Done. Logs: $LOG_DIR"
echo "[DE] Kill Name Server locally, scancel for the rest: scancel $SLURM_JOB_ID"
kill "$NS_PID" 2>/dev/null || true
scancel "$SLURM_JOB_ID" 2>/dev/null || true
