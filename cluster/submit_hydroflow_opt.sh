#!/usr/bin/env bash
#SBATCH --job-name=hydroflow_opt
#SBATCH --output=hydroflow_opt_%j.out
#SBATCH --time=48:00:00
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --exclusive
#SBATCH --partition=cpu
#
# One hydroflow-opt optimization on a single node.
#
#   sbatch cluster/submit_hydroflow_opt.sh cluster/configs/tistos-cfd-only.toml
#
# No --mem at all. A fixed figure is rejected outright on the smaller partition
# ("Memory required by task is not available"), and --mem=0 is not accepted
# everywhere either. --exclusive grants the node and its memory on both.
# --exclusive for the same reason: a fixed --cpus-per-task=96 is rejected on a
# 64-core node. Taking the whole node works on either, and the script scales the
# config down to however many cores the allocation actually grants. hydroflow-opt has only a SubprocessBackend, so a run lives on ONE node —
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

# A config sized for a bigger partition is scaled down rather than rejected.
# Parallelism decides wall time, not results: the seed, the population and the
# candidates are unchanged, so the same config is valid on any partition and you
# can submit wherever nodes happen to be free.
if (( CFG_CPUS > ALLOC_CPUS )); then
    NEW_THREADS=$(( ALLOC_CPUS / (CFG_CONC * CFG_RANKS) ))
    NEW_CONC=$CFG_CONC
    if (( NEW_THREADS < 1 )); then
        NEW_THREADS=1
        NEW_CONC=$(( ALLOC_CPUS / CFG_RANKS ))
        # islands must not exceed concurrent_evaluations (runner.py:519-526).
        (( NEW_CONC < CFG_ISLANDS )) && NEW_CONC=$CFG_ISLANDS
    fi
    echo "[submit] scaling to the allocation: cpus $CFG_CPUS -> $ALLOC_CPUS," \
         "concurrent $CFG_CONC -> $NEW_CONC, threads $CFG_THREADS -> $NEW_THREADS"
    if (( NEW_CONC * CFG_RANKS * NEW_THREADS > ALLOC_CPUS )); then
        echo "[submit] ERROR: cannot fit $CFG_ISLANDS islands x $CFG_RANKS ranks" \
             "into $ALLOC_CPUS cpus. Lower optimization.islands or mpi_ranks." >&2
        exit 1
    fi
    CFG_CPUS=$ALLOC_CPUS; CFG_CONC=$NEW_CONC; CFG_THREADS=$NEW_THREADS
    SCALE_RESOURCES=1
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
if [[ "${SCALE_RESOURCES:-0}" == "1" ]]; then
    sed -i -e "s|^available_cpus *=.*|available_cpus = $CFG_CPUS|" \
           -e "s|^concurrent_evaluations *=.*|concurrent_evaluations = $CFG_CONC|" \
           -e "s|^threads_per_rank *=.*|threads_per_rank = $CFG_THREADS|" "$RUN_CONFIG"
fi
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

# ── Images unpacked onto node-local disk ──────────────────────────────────
# enroot mounts a .sqsh through squashfuse — a userspace FUSE mount that
# decompresses every read in a single process. Measured on a compute node:
# squashfuse at 37% CPU while dtOO's CreateStates, which takes 8 seconds against
# an unpacked image, had not finished after 20 minutes. Copying the .sqsh to
# local disk removed the Lustre latency but not the FUSE layer.
#
# `enroot create` unpacks the image into a plain directory once per job. It
# costs ~7 GB of the node's NVMe and a couple of minutes, against every file
# read of every candidate paying decompression otherwise.
export ENROOT_IMAGES="${ENROOT_IMAGES:-$WS/enroot-images}"
if [[ "${DRY_RUN:-0}" != "1" && -n "${TMPDIR:-}" && "${STAGE_IMAGES:-1}" == "1" ]]; then
    export ENROOT_DATA_PATH="$TMPDIR/enroot-data"
    mkdir -p "$ENROOT_DATA_PATH"
    n_images=0
    for img in "$ENROOT_IMAGES"/*.sqsh; do
        # An unmatched glob reaches the loop as the literal pattern. Without the
        # counter below that is silent: no container is created, no error is
        # raised, and the first candidate dies on a container it cannot find.
        [[ -f "$img" ]] || continue
        n_images=$((n_images + 1))
        name="$(basename "$img" .sqsh)"
        echo "[submit] unpacking $name"
        enroot create --name "$name" "$img" || {
            echo "[submit] enroot create failed for $name" >&2; exit 1; }
    done
    if (( n_images == 0 )); then
        echo "[submit] ERROR: no .sqsh found in $ENROOT_IMAGES — import per" >&2
        echo "[submit]        cluster/enroot_dtoo_import.md and cluster/enroot_fenicsx_import.md" >&2
        exit 1
    fi
    echo "[submit] containers -> $ENROOT_DATA_PATH ($(du -sh "$ENROOT_DATA_PATH" | cut -f1))"
    echo "[submit] configs must name the container, not a path: dtOO / dolfinx"
else
    # A warning, not an error: the documented login-node DRY_RUN (see the
    # "Order of work" section of cluster/enroot_fenicsx_import.md) runs without
    # a TMPDIR and must keep working.
    echo "[submit] WARNING: image staging skipped (DRY_RUN=${DRY_RUN:-0}, TMPDIR=${TMPDIR:-<unset>}, STAGE_IMAGES=${STAGE_IMAGES:-1})." >&2
    echo "[submit]          enroot start by NAME then needs its containers from elsewhere." >&2
fi

# Every container NAME a config asks for needs a matching .sqsh basename, or the
# run dies at the first candidate with a cryptic enroot error. Checked outside
# the staging branch on purpose, so a login-node DRY_RUN catches it too.
WANTED_CONTAINERS="$("$VENV/bin/python" - "$RUN_CONFIG" <<'PY'
import sys, tomllib
raw = tomllib.load(open(sys.argv[1], "rb"))
opts = raw.get("case", {}).get("options", {})
for sec in ("dtoo", "modal", "cfd"):
    want = (opts.get(sec) or {}).get("container")
    if want and "/" not in str(want):
        print(want)
PY
)"
while read -r want; do
    [[ -z "$want" ]] && continue
    if [[ ! -f "$ENROOT_IMAGES/$want.sqsh" ]]; then
        echo "[submit] ERROR: config wants container '$want' but $ENROOT_IMAGES/$want.sqsh is missing." >&2
        echo "[submit]        Have: $(find "$ENROOT_IMAGES" -maxdepth 1 -name '*.sqsh' -printf '%f ' 2>/dev/null)" >&2
        exit 1
    fi
done <<< "$WANTED_CONTAINERS"

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
#
# `|| EXIT_CODE=$?` rather than a bare capture afterwards: under `set -e` a
# failing hydroflow-opt ends the script right there and the post-mortem echo
# below — the one line that says what happened — never reaches the .out.
EXIT_CODE=0
if [[ "$CFG_MODE" == "optimize" && -f "$ABS_RUN_DIR/manifest.json" ]]; then
    echo "[submit] ---- resume ----"
    "$VENV/bin/hydroflow-opt" resume "$ABS_RUN_DIR" || EXIT_CODE=$?
else
    echo "[submit] ---- $CFG_MODE ----"
    "$VENV/bin/hydroflow-opt" "$CFG_MODE" "$RUN_CONFIG" || EXIT_CODE=$?
fi

echo "[submit] hydroflow-opt exit code: $EXIT_CODE"
echo "[submit]"
echo "[submit] Sanity gate before anyone looks at the result — a metric with a"
echo "[submit] unique count of 1 across all generations is frozen, not converged:"
echo "[submit]   python3 $REPO/cluster/summarize_run.py <run_dir>"
exit $EXIT_CODE
