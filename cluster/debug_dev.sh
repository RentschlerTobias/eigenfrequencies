#!/usr/bin/env bash
#SBATCH --partition=dev_cpu_il
#SBATCH --time=00:30:00
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=12
#SBATCH --output=cluster/logs/latest/slurm-%j.out
#SBATCH --error=cluster/logs/latest/slurm-%j.err
#
# One-command sbatch debug harness for the 2-candidate CFD smoke.
#
#   cd ${EIGENFREQUENCIES_REPO} && sbatch cluster/debug_dev.sh
#   cd ${EIGENFREQUENCIES_REPO} && EVAL_CONFIG=cfd sbatch cluster/debug_dev.sh
#
# DRY_RUN=1 validates everything locally without submitting:
#
#   DRY_RUN=1 WS=/tmp/fake-qa bash cluster/debug_dev.sh

set -euo pipefail

# Absolute repo root derived from this script, same pattern as batch_env.sh.
REPO="${EIGENFREQUENCIES_REPO:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"

# SLURM sets this in batch; default to DRYTEST for local QA so set -u stays safe.
SLURM_JOB_ID="${SLURM_JOB_ID:-DRYTEST}"

# SLURM writes to cluster/logs/latest/ relative to the submission CWD. Ensure it
# exists even if the worktree is checked out fresh, and keep it absolute.
LATEST_DIR="$REPO/cluster/logs/latest"
mkdir -p "$LATEST_DIR"

# Batch-safe environment: provisions WS, ENROOT_* and EIGENFREQUENCIES_REPO.
source "$REPO/cluster/batch_env.sh"

# Resolve debug configuration.
EVAL_CONFIG="${EVAL_CONFIG:-native}"
case "$EVAL_CONFIG" in
    native)
        CONFIG="cluster/configs/tistos-smoke-cfd-native.toml"
        ;;
    cfd)
        CONFIG="cluster/configs/tistos-smoke-cfd.toml"
        ;;
    *)
        echo "usage: EVAL_CONFIG=native|cfd sbatch $0" >&2
        exit 64
        ;;
esac
CONFIG="$REPO/$CONFIG"

BASENAME="$(basename "$CONFIG" .toml)"
RUN_DIR="$WS/runs/$BASENAME"

# Timestamped archive of the previous run/scratch/local dirs for this config.
# Mirrors rerun_smoke.sh: only the selected config's artifacts are moved.
archive_previous() {
    local stamp suffix dir
    stamp="$(date +%Y%m%d-%H%M%S)"
    ARCHIVE_DIR="$WS/runs/archive-$stamp"
    local moved=0
    for suffix in "" "-scratch" "-local"; do
        dir="$WS/runs/$BASENAME$suffix"
        if [ -e "$dir" ]; then
            mkdir -p "$ARCHIVE_DIR"
            mv "$dir" "$ARCHIVE_DIR/" && {
                echo "[debug_dev] archived $(basename "$dir") -> $ARCHIVE_DIR"
                moved=1
            }
        fi
    done
    if [ "$moved" -eq 0 ]; then
        rmdir "$ARCHIVE_DIR" 2>/dev/null || true
        ARCHIVE_DIR=""
    fi
}

# Read run.directory and case.options.local_scratch from the TOML.
# Both may contain $WS variables; python3 os.path.expandvars resolves them.
read_config_paths() {
    local parsed
    parsed="$(python3 - "$CONFIG" <<'PY'
import os, sys, tomllib
raw = tomllib.load(open(sys.argv[1], "rb"))
run_dir = os.path.expandvars(raw.get("run", {}).get("directory", ""))
local_scratch = os.path.expandvars(raw.get("case", {}).get("options", {}).get("local_scratch", ""))
print(run_dir)
print(local_scratch)
PY
    )"
    RUN_DIR="$(printf '%s\n' "$parsed" | sed -n '1p')"
    LOCAL_SCRATCH="$(printf '%s\n' "$parsed" | sed -n '2p')"
}

# Validate the config in DRY_RUN without invoking hydroflow-opt.
dry_run_validate() {
    if [ ! -f "$CONFIG" ]; then
        echo "[debug_dev] ERROR: config not found: $CONFIG" >&2
        exit 1
    fi
    python3 - "$CONFIG" <<'PY'
import sys, tomllib
raw = tomllib.load(open(sys.argv[1], "rb"))
# Sanity-check the fields this harness reads.
_ = raw["run"]["directory"]
_ = raw["case"]["options"]["local_scratch"]
PY
    if [ -z "${WS:-}" ]; then
        echo "[debug_dev] ERROR: WS is empty after batch_env.sh" >&2
        exit 1
    fi
}

# Per-stage log summary in rerun_smoke.sh style.
stage_summary() {
    local scratch="$1"
    local log candidate
    if [ -z "$scratch" ] || [ ! -d "$scratch" ]; then
        echo "stage_logs=none"
        return
    fi
    for candidate in "$scratch"/*/; do
        [ -d "$candidate" ] || continue
        for log in "$candidate"logs/*.log; do
            [ -f "$log" ] || continue
            local rel="${log#"$scratch"/}"
            echo "stage: $rel ($(wc -l < "$log") lines)"
            head -1 "$log" | cut -c1-200 | sed 's/^/  /'
        done
    done
}

# Print the final machine-readable summary block.
print_summary() {
    local job_label="$1"
    shift
    echo "=== debug_dev summary (job=$job_label) ==="
    echo "eval_config=$EVAL_CONFIG"
    echo "config=$CONFIG"
    echo "run_dir=$RUN_DIR"
    echo "local_scratch=${LOCAL_SCRATCH:-<unset>}"
    echo "log_dir=$LOG_DIR"
    if [ -n "${ARCHIVE_DIR:-}" ]; then
        echo "archive_dir=$ARCHIVE_DIR"
    fi
    echo "submit_exit=${EXIT_CODE:-SKIPPED}"
    echo "probe_rc=${PROBE_RC:-SKIPPED}"
    stage_summary "${LOCAL_SCRATCH:-}"
}

# Archive any stale artifacts for this config before the new run.
archive_previous

read_config_paths

LOG_DIR="$REPO/cluster/logs/$SLURM_JOB_ID"
mkdir -p "$LOG_DIR"

if [ "${DRY_RUN:-0}" = "1" ]; then
    dry_run_validate
    print_summary "DRY"
    exit 0
fi

# Non-DRY_RUN: invoke the smoke submit script and keep collecting evidence even
# if the smoke itself fails. Mirror submit_hydroflow_opt.sh:286-293 capture.
EXIT_CODE=0
bash "$REPO/cluster/submit_hydroflow_opt.sh" "$CONFIG" || EXIT_CODE=$?

# Enroot-only probe for the containerised smoke.
PROBE_RC=SKIPPED
if [ "$EVAL_CONFIG" = "cfd" ]; then
    export PROBE_OUT="$REPO/cluster/logs/$SLURM_JOB_ID/probe-solve-shell"
    export WORK="$WS/runs/tistos-smoke-cfd-local/baseline"
    PROBE_RC=0
    bash "$REPO/cluster/probe_solve_shell.sh" || PROBE_RC=$?
fi

# Move this job's SLURM .out/.err from cluster/logs/latest into the job log dir.
if [ -f "$LATEST_DIR/slurm-$SLURM_JOB_ID.out" ]; then
    mv "$LATEST_DIR/slurm-$SLURM_JOB_ID.out" "$LOG_DIR/"
fi
if [ -f "$LATEST_DIR/slurm-$SLURM_JOB_ID.err" ]; then
    mv "$LATEST_DIR/slurm-$SLURM_JOB_ID.err" "$LOG_DIR/"
fi

# Replace the latest/ directory with a symlink to this job.
if [ -e "$LATEST_DIR" ] || [ -L "$LATEST_DIR" ]; then
    rm -rf "$LATEST_DIR"
fi
ln -s "$SLURM_JOB_ID" "$LATEST_DIR"

# Copy per-candidate stage logs and the top-level results.jsonl into the log dir.
if [ -n "${LOCAL_SCRATCH:-}" ] && [ -d "$LOCAL_SCRATCH" ]; then
    mkdir -p "$LOG_DIR/stage-logs"
    cp -r "$LOCAL_SCRATCH"/*/logs/. "$LOG_DIR/stage-logs/" 2>/dev/null || true
fi
if [ -n "${RUN_DIR:-}" ] && [ -f "$RUN_DIR/results.jsonl" ]; then
    cp "$RUN_DIR/results.jsonl" "$LOG_DIR/" 2>/dev/null || true
fi

# Post-run evidence extraction (todo 4) is called only when defined.
if declare -F collect_evidence >/dev/null; then
    collect_evidence "$LOG_DIR"
fi

print_summary "$SLURM_JOB_ID"

exit "${EXIT_CODE:-0}"
