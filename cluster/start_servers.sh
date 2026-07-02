#!/bin/bash
# Start Pyro5 Name Server and DE worker servers on a single node.
#
# Usage:
#   bash cluster/start_servers.sh [N_WORKERS]
#
# Default N_WORKERS=20 (matches DEConfig.pop_size). Each worker is a
# persistent Pyro5 server process registered with the Name Server.

set -e

source ~/pe

# Ensure we are in the repo root regardless of where the script is invoked
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

NS_HOST=$(hostname)
N_WORKERS=${1:-20}

LOG_DIR="$REPO_ROOT/server_logs"
mkdir -p "$LOG_DIR"

echo "[DE] Starting Name Server on $NS_HOST..."
pyro5-ns -n "$NS_HOST" > "$LOG_DIR/nameserver.log" 2>&1 &
NS_PID=$!
sleep 3

echo "[DE] Starting $N_WORKERS workers..."
for i in $(seq 0 $((N_WORKERS-1))); do
    python3 turbine_runner/server_de.py "$i" "$NS_HOST" > "$LOG_DIR/worker_${i}.log" 2>&1 &
done

echo "[DE] Name Server PID: $NS_PID"
echo "[DE] $N_WORKERS workers started on $NS_HOST"
echo "[DE] Logs: $LOG_DIR"
echo ""
echo "Start client with:"
echo "  export PYRO_NS_HOST=$NS_HOST"
echo "  python3 turbine_runner/optimize_de.py"
