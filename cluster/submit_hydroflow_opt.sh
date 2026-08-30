#!/usr/bin/env bash
#SBATCH --job-name=hydroflow_opt
#SBATCH --output=hydroflow_opt_%j.out
#SBATCH --time=48:00:00
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=64
#SBATCH --mem=240G
#SBATCH --partition=dev_cpu_il
#
# One hydroflow-opt optimization on a single node.
#
#   sbatch cluster/submit_hydroflow_opt.sh cluster/configs/tistos-cfd-only.toml
#
# Sized for cpu_il / dev_cpu_il: Intel Xeon Platinum 8358, 64 cores, 256 GiB,
# 1.8 TB local NVMe. [USER] Other partitions differ — the script verifies the
# #SBATCH lines against the config's [resources] before starting anything, so a
# mismatch costs seconds instead of a run.
#
# Run order matters: cfd-only, then freq-only, then combined. See
# cluster/configs/README.md.

set -euo pipefail

CONFIG="${1:-}"
if [[ -z "$CONFIG" ]]; then
    echo "usage: sbatch $0 CONFIG.toml" >&2
    exit 2
fi
if [[ ! -f "$CONFIG" ]]; then
    echo "[submit] ERROR: config not found: $CONFIG" >&2
    exit 2
fi

REPO="${EIGENFREQUENCIES_REPO:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
# [USER] The venv holding hydroflow-opt + eigenfrequencies[hydroflow].
VENV="${HYDROFLOW_VENV:-$HOME/venvs/hydroflow}"

echo "========================================"
echo "[submit] host=$(hostname 2>/dev/null || echo unknown) job=${SLURM_JOB_ID:-none}"
echo "[submit] config=$CONFIG"
echo "[submit] repo=$REPO"
echo "[submit] venv=$VENV"
echo "========================================"

if [[ ! -x "$VENV/bin/hydroflow-opt" ]]; then
    echo "[submit] ERROR: hydroflow-opt not found in $VENV" >&2
    echo "[submit] See cluster/enroot_fenicsx_import.md section 6." >&2
    exit 1
fi

# ── Resource check ────────────────────────────────────────────────────────
# hydroflow-opt validates concurrent × ranks × threads ≤ available_cpus itself,
# but it has no idea what SLURM actually granted. A config claiming 40 cores in
# a 20-core allocation passes its check and then oversubscribes the node.

read -r CFG_CPUS CFG_CONC CFG_RANKS CFG_THREADS CFG_ISLANDS CFG_MODE <<<"$(
    "$VENV/bin/python" - "$CONFIG" <<'PY'
import sys, tomllib
raw = tomllib.load(open(sys.argv[1], "rb"))
res = raw.get("resources", {})
opt = raw.get("optimization", {})
# The two hydroflow-opt entry points take different configs: `optimize` needs an
# [optimization] table, `run` needs [[candidate]] entries. Picking the wrong one
# fails after the allocation is already granted, so let the config decide.
mode = "optimize" if "optimization" in raw else ("run" if raw.get("candidate") else "none")
print(res.get("available_cpus", 1), res.get("concurrent_evaluations", 1),
      res.get("mpi_ranks", 1), res.get("threads_per_rank", 1),
      opt.get("islands", 1), mode)
PY
)"

if [[ "$CFG_MODE" == "none" ]]; then
    echo "[submit] ERROR: $CONFIG has neither [optimization] nor [[candidate]]." >&2
    exit 1
fi

ALLOC_CPUS="${SLURM_CPUS_PER_TASK:-${SLURM_CPUS_ON_NODE:-$(nproc)}}"
if [[ -n "${SLURM_MEM_PER_NODE:-}" ]]; then
    ALLOC_MEM_GB=$(( SLURM_MEM_PER_NODE / 1024 ))
else
    ALLOC_MEM_GB=$(( $(awk '/MemTotal/ {print $2}' /proc/meminfo) / 1024 / 1024 ))
fi

echo "[submit] config:     cpus=$CFG_CPUS concurrent=$CFG_CONC ranks=$CFG_RANKS threads=$CFG_THREADS islands=$CFG_ISLANDS mode=$CFG_MODE"
echo "[submit] allocation: cpus=$ALLOC_CPUS mem=${ALLOC_MEM_GB}G"

if (( CFG_CPUS > ALLOC_CPUS )); then
    echo "[submit] ERROR: config claims $CFG_CPUS cpus, allocation has $ALLOC_CPUS." >&2
    echo "[submit] Fix [resources].available_cpus or --cpus-per-task." >&2
    exit 1
fi
if [[ "$CFG_MODE" == "optimize" ]] && (( CFG_ISLANDS > CFG_CONC )); then
    echo "[submit] ERROR: islands ($CFG_ISLANDS) > concurrent_evaluations ($CFG_CONC)." >&2
    exit 1
fi

# ~10 GB peak per modal solve: MUMPS' own figure for the tistos matrix at P2,
# 545247 DOFs, measured rather than extrapolated (INFOG(22) = 10169 MB, see
# .omo/evidence/task-modal-memory.md). Still only a warning — a different mesh
# or element degree moves it, and cfd_only does no modal solve at all.
MODAL_GB="${MODAL_PEAK_GB:-11}"
if grep -qE 'eval_mode *= *"(combined|resonance_only)"' "$CONFIG"; then
    NEEDED=$(( CFG_CONC * MODAL_GB ))
    if (( NEEDED > ALLOC_MEM_GB )); then
        echo "[submit] WARNING: $CFG_CONC concurrent modal solves need ~${NEEDED}G," >&2
        echo "[submit]          allocation has ${ALLOC_MEM_GB}G. Expect OOM kills." >&2
        echo "[submit]          Lower concurrent_evaluations (and islands with it)." >&2
    fi
fi

# ── Scratch on node-local disk ────────────────────────────────────────────
# One candidate leaves a 21 MB mesh and a decomposed OpenFOAM case behind. That
# belongs on $TMPDIR, not on the shared workspace. Results are unaffected: the
# orchestrator writes them to [run].directory.
# The run directory is always rewritten, never left as written. hydroflow-opt
# resolves a relative path against the *config file's* parent (config.py:74-79)
# and expands no variables at all, so "$WS/runs/x" would be taken literally —
# results would land in a directory called '$WS' inside the repo.
RENDER_DIR="${TMPDIR:-/tmp}"
RUN_CONFIG="$RENDER_DIR/$(basename "$CONFIG")"
CONFIG_DIR="$(cd "$(dirname "$CONFIG")" && pwd)"
RAW_RUN_DIR="$("$VENV/bin/python" -c \
    'import sys,tomllib;print(tomllib.load(open(sys.argv[1],"rb"))["run"]["directory"])' \
    "$CONFIG")"
ABS_RUN_DIR="$(eval echo "$RAW_RUN_DIR")"          # expands $WS / $HOME / ~
case "$ABS_RUN_DIR" in
    /*) : ;;
    *)  ABS_RUN_DIR="$CONFIG_DIR/$ABS_RUN_DIR" ;;
esac
mkdir -p "$ABS_RUN_DIR"

sed -e "s|^directory *=.*|directory = \"$ABS_RUN_DIR\"|" "$CONFIG" > "$RUN_CONFIG"
echo "[submit] results  -> $ABS_RUN_DIR"

# Scratch on node-local disk: one candidate leaves a 21 MB mesh and a decomposed
# OpenFOAM case behind, which does not belong on the shared workspace.
if [[ -n "${TMPDIR:-}" && "${KEEP_SCRATCH:-0}" != "1" ]]; then
    SCRATCH="$TMPDIR/hydroflow-scratch"
    mkdir -p "$SCRATCH"
    if grep -q '^scratch_directory' "$RUN_CONFIG"; then
        sed -i "s|^scratch_directory *=.*|scratch_directory = \"$SCRATCH\"|" "$RUN_CONFIG"
    else
        sed -i "0,/^\[run\]/s|^\[run\]|[run]\nscratch_directory = \"$SCRATCH\"|" "$RUN_CONFIG"
    fi
    echo "[submit] scratch  -> $SCRATCH (KEEP_SCRATCH=1 to disable)"
fi

# The case plugin resolves the machine catalog relative to the installed
# package; point it at this checkout so an installed copy still finds tistos.yaml.
export EIGENFREQUENCIES_MACHINES_DIR="$REPO/adapters/machines"
export EIGENFREQUENCIES_REPO="$REPO"

echo "[submit] ---- check ----"
"$VENV/bin/hydroflow-opt" check "$RUN_CONFIG"

# DRY_RUN=1 stops here: everything is validated — resources, config, case
# discovery, scratch layout — without spending the allocation. Worth doing once
# on a login node before queueing a 48-hour job.
if [[ "${DRY_RUN:-0}" == "1" ]]; then
    echo "[submit] DRY_RUN=1 — stopping after check, nothing evaluated."
    exit 0
fi

echo "[submit] ---- $CFG_MODE ----"
"$VENV/bin/hydroflow-opt" "$CFG_MODE" "$RUN_CONFIG"
EXIT_CODE=$?

echo "[submit] hydroflow-opt exit code: $EXIT_CODE"
echo "[submit]"
echo "[submit] Sanity gate before anyone looks at the result — a metric with a"
echo "[submit] unique count of 1 across all generations is frozen, not converged:"
echo "[submit]   python3 $REPO/cluster/summarize_run.py <run_dir>"
exit $EXIT_CODE
