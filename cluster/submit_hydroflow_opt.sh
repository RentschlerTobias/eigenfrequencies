#!/usr/bin/env bash
#SBATCH --job-name=hydroflow_opt
#SBATCH --output=hydroflow_opt_%j.out
#SBATCH --time=48:00:00
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=96
#SBATCH --mem=370G
#SBATCH --partition=cpu
#
# One hydroflow-opt optimization on a single node.
#
#   sbatch cluster/submit_hydroflow_opt.sh cluster/configs/tistos-cfd-only.toml
#
# Sized for the cpu partition: AMD EPYC 9454, 96 cores, 384 GiB, 3.84 TB local
# NVMe. hydroflow-opt has only a SubprocessBackend, so a run lives on ONE node —
# more nodes would sit idle; a bigger node and more concurrency are the levers. [USER] Other partitions differ — the script verifies the
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
# Deliberately NOT created here: hydroflow-opt refuses to start an optimization
# in a directory that already has anything in it, and it makes the directory
# itself.

sed -e "s|^directory *=.*|directory = \"$ABS_RUN_DIR\"|" "$CONFIG" > "$RUN_CONFIG"
echo "[submit] results  -> $ABS_RUN_DIR"

# The orchestrator's scratch directory stays on the workspace, stable across
# jobs. It is part of every request, and the request is the cache key that lets
# `resume` reuse a finished evaluation instead of recomputing it — pointed at
# $TMPDIR it would differ in every job and resume would save nothing.
#
# The heavy per-candidate artifacts still go to node-local disk: the worker
# reads case.options.local_scratch and works in $TMPDIR/<candidate-id>.
# Beside the run directory, not inside it — anything inside makes
# `optimize` abort with "optimization run directory is not empty".
SCRATCH="${ABS_RUN_DIR}-scratch"
mkdir -p "$SCRATCH"
if grep -q '^scratch_directory' "$RUN_CONFIG"; then
    sed -i "s|^scratch_directory *=.*|scratch_directory = \"$SCRATCH\"|" "$RUN_CONFIG"
else
    sed -i "0,/^\[run\]/s|^\[run\]|[run]\nscratch_directory = \"$SCRATCH\"|" "$RUN_CONFIG"
fi
echo "[submit] scratch  -> $SCRATCH (stable, so resume can reuse results)"

# ── Images onto node-local disk ───────────────────────────────────────────
# Read through squashfuse from the parallel filesystem, the dtOO export ran past
# its 900 s timeout — the same export takes ~300 s when the image is local. The
# nodes have 1.8 TB of NVMe; copying 5.5 GB once beats every evaluation paying
# for it, and with eight concurrent candidates they would all pay at once.
export ENROOT_IMAGES="${ENROOT_IMAGES:-$WS/enroot-images}"
if [[ -n "${TMPDIR:-}" && "${STAGE_IMAGES:-1}" == "1" ]]; then
    LOCAL_IMAGES="$TMPDIR/enroot-images"
    mkdir -p "$LOCAL_IMAGES"
    for img in "$ENROOT_IMAGES"/*.sqsh; do
        [[ -f "$img" ]] || continue
        echo "[submit] staging $(basename "$img") -> $LOCAL_IMAGES"
        cp "$img" "$LOCAL_IMAGES/" || { echo "[submit] staging failed" >&2; exit 1; }
    done
    export ENROOT_IMAGES="$LOCAL_IMAGES"
    echo "[submit] images   -> $ENROOT_IMAGES ($(du -sh "$LOCAL_IMAGES" | cut -f1))"
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

# A run directory with a manifest is an interrupted optimization, not a new one.
# Resuming picks up at the last checkpoint and reuses every evaluation that
# finished, so a walltime kill costs at most the generation in progress — and
# the population can be sized for the problem instead of for 48 hours.
if [[ "$CFG_MODE" == "optimize" && -f "$ABS_RUN_DIR/manifest.json" ]]; then
    echo "[submit] ---- resume ----"
    "$VENV/bin/hydroflow-opt" resume "$ABS_RUN_DIR"
else
    echo "[submit] ---- $CFG_MODE ----"
    "$VENV/bin/hydroflow-opt" "$CFG_MODE" "$RUN_CONFIG"
fi
EXIT_CODE=$?

echo "[submit] hydroflow-opt exit code: $EXIT_CODE"
echo "[submit]"
echo "[submit] Sanity gate before anyone looks at the result — a metric with a"
echo "[submit] unique count of 1 across all generations is frozen, not converged:"
echo "[submit]   python3 $REPO/cluster/summarize_run.py <run_dir>"
exit $EXIT_CODE
