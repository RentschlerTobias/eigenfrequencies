#!/bin/bash
# Convenience script: start Pyro5 Name Server + workers, then run DE client.
#
# Usage:
#   bash cluster/run_de.sh [POP_SIZE] [MAX_GEN] [SEED]
#
# Defaults: POP_SIZE=4, MAX_GEN=2, SEED=42 (quick smoke test)
# For full DE: bash cluster/run_de.sh 20 30

set -e

# ── cd to repo root ──
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

# ── Source environment ──
# NOTE: source must run in the SAME shell as the python calls below.
source ~/pe
PYTHON=$(which python3)

echo "[DE] Python: $PYTHON"

# ── Defaults ──
POP_SIZE="${1:-4}"
MAX_GEN="${2:-2}"
SEED="${3:-42}"
NS_HOST=$(hostname)

export PYRO_NS_HOST="$NS_HOST"
export CFD_CASE_DIR="${CFD_CASE_DIR:-}"
export DE_POP_SIZE="$POP_SIZE"
export DE_MAX_GEN="$MAX_GEN"
export DE_SEED="$SEED"

# ── Clean old logs ──
LOG_DIR="$REPO_ROOT/server_logs"
rm -rf "$LOG_DIR"
mkdir -p "$LOG_DIR"

echo "========================================"
echo "[DE] Starting Pyro5 DE on $NS_HOST"
echo "[DE] POP_SIZE=$POP_SIZE  MAX_GEN=$MAX_GEN  SEED=$SEED"
echo "[DE] CFD_CASE_DIR=$CFD_CASE_DIR"
echo "========================================"

# ── Start Name Server ──
echo "[DE] Starting Name Server..."
pyro5-ns -n "$NS_HOST" > "$LOG_DIR/nameserver.log" 2>&1 &
NS_PID=$!
sleep 3

# ── Start workers ──
echo "[DE] Starting $POP_SIZE workers..."
for i in $(seq 0 $((POP_SIZE-1))); do
    $PYTHON turbine_runner/server_de.py "$i" "$NS_HOST" > "$LOG_DIR/worker_${i}.log" 2>&1 &
done

sleep 2

# ── Run DE client ──
echo "[DE] Running DE client..."
$PYTHON turbine_runner/optimize_de.py

# ── Cleanup hint ──
echo ""
echo "[DE] Done. Logs: $LOG_DIR"
echo "[DE] Kill Name Server: kill $NS_PID"
echo "[DE] Kill workers: pkill -f server_de.py"
