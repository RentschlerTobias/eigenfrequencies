#!/usr/bin/env bash
#SBATCH --job-name=hydroflow_opt
#SBATCH --output=hydroflow_opt_%j.out
#SBATCH --time=48:00:00
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=40
#SBATCH --mem=90G
#SBATCH --partition=cpu_il
#
# One hydroflow-opt optimization on a single node.
#
#   sbatch cluster/submit_hydroflow_opt.sh cluster/configs/tistos-cfd-only.toml
#
# [USER] The four #SBATCH resource lines above are sized for a 40-core / 96 GB
# node and must match the partition you actually use — check with
# `sinfo -o "%P %c %m %l"`. They have to agree with the [resources] table of the
# config; this script verifies that before starting anything, so a mismatch
# costs seconds instead of a run.
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

read -r CFG_CPUS CFG_CONC CFG_RANKS CFG_THREADS CFG_ISLANDS <<<"$(
    "$VENV/bin/python" - "$CONFIG" <<'PY'
import sys, tomllib
raw = tomllib.load(open(sys.argv[1], "rb"))
res = raw.get("resources", {})
opt = raw.get("optimization", {})
print(res.get("available_cpus", 1), res.get("concurrent_evaluations", 1),
      res.get("mpi_ranks", 1), res.get("threads_per_rank", 1),
      opt.get("islands", 1))
PY
)"

ALLOC_CPUS="${SLURM_CPUS_PER_TASK:-${SLURM_CPUS_ON_NODE:-$(nproc)}}"
if [[ -n "${SLURM_MEM_PER_NODE:-}" ]]; then
    ALLOC_MEM_GB=$(( SLURM_MEM_PER_NODE / 1024 ))
else
    ALLOC_MEM_GB=$(( $(awk '/MemTotal/ {print $2}' /proc/meminfo) / 1024 / 1024 ))
fi

echo "[submit] config:     cpus=$CFG_CPUS concurrent=$CFG_CONC ranks=$CFG_RANKS threads=$CFG_THREADS islands=$CFG_ISLANDS"
echo "[submit] allocation: cpus=$ALLOC_CPUS mem=${ALLOC_MEM_GB}G"

if (( CFG_CPUS > ALLOC_CPUS )); then
    echo "[submit] ERROR: config claims $CFG_CPUS cpus, allocation has $ALLOC_CPUS." >&2
    echo "[submit] Fix [resources].available_cpus or --cpus-per-task." >&2
    exit 1
fi
if (( CFG_ISLANDS > CFG_CONC )); then
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
RUN_CONFIG="$CONFIG"
if [[ -n "${TMPDIR:-}" && "${KEEP_SCRATCH:-0}" != "1" ]]; then
    RUN_CONFIG="$TMPDIR/$(basename "$CONFIG")"
    SCRATCH="$TMPDIR/hydroflow-scratch"
    mkdir -p "$SCRATCH"

    # hydroflow-opt resolves relative paths against the *config file's* parent
    # (config.py:74-79). Moving the config to $TMPDIR would therefore move the
    # results there too — onto a disk that is wiped when the job ends. Pin the
    # run directory to an absolute path first.
    CONFIG_DIR="$(cd "$(dirname "$CONFIG")" && pwd)"
    REL_RUN_DIR="$("$VENV/bin/python" -c \
        'import sys,tomllib;print(tomllib.load(open(sys.argv[1],"rb"))["run"]["directory"])' \
        "$CONFIG")"
    case "$REL_RUN_DIR" in
        /*) ABS_RUN_DIR="$REL_RUN_DIR" ;;
        *)  ABS_RUN_DIR="$CONFIG_DIR/$REL_RUN_DIR" ;;
    esac

    sed -e "s|^directory *=.*|directory = \"$ABS_RUN_DIR\"|" \
        -e "s|^scratch_directory *=.*|scratch_directory = \"$SCRATCH\"|" \
        "$CONFIG" > "$RUN_CONFIG"
    if ! grep -q '^scratch_directory' "$RUN_CONFIG"; then
        sed -i "0,/^\[run\]/s|^\[run\]|[run]\nscratch_directory = \"$SCRATCH\"|" "$RUN_CONFIG"
    fi
    echo "[submit] results  -> $ABS_RUN_DIR"
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

echo "[submit] ---- optimize ----"
"$VENV/bin/hydroflow-opt" optimize "$RUN_CONFIG"
EXIT_CODE=$?

echo "[submit] hydroflow-opt exit code: $EXIT_CODE"
echo "[submit]"
echo "[submit] Sanity gate before anyone looks at the result — a metric with a"
echo "[submit] unique count of 1 across all generations is frozen, not converged:"
echo "[submit]   python3 $REPO/cluster/summarize_run.py <run_dir>"
exit $EXIT_CODE
