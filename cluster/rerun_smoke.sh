#!/usr/bin/env bash
# Archive the previous smoke run and start a fresh one.
#
#     bash cluster/rerun_smoke.sh [CONFIG]
#
# Default CONFIG: cluster/configs/tistos-smoke-cfd.toml
#
# hydroflow-opt refuses to start in a run directory that already holds
# anything, so a repeat needs the previous one out of the way. Three
# directories, not one:
#
#   <run>            the results
#   <run>-scratch    the orchestrator's cache — left behind, a rerun can be
#                    served from it and the gate would pass without the
#                    container having run at all
#   <run>-local      the candidate working directories with every stage log
#
# Nothing is deleted, everything is renamed with a timestamp. Typing the three
# `mv` lines by hand went wrong often enough to be worth a script.

set -uo pipefail

CONFIG="${1:-cluster/configs/tistos-smoke-cfd.toml}"
REPO="${EIGENFREQUENCIES_REPO:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"

[ -f "$CONFIG" ] || { echo "no config at $CONFIG" >&2; exit 2; }
[ -n "${WS:-}" ] || { echo "WS unset — run: source cluster/interactive_setup.sh" >&2; exit 1; }

RUN_DIR="$("$(command -v python3)" - "$CONFIG" <<'PY'
import os, sys, tomllib
raw = tomllib.load(open(sys.argv[1], "rb"))
print(os.path.expandvars(raw["run"]["directory"]))
PY
)"
[ -n "$RUN_DIR" ] || { echo "cannot read [run] directory from $CONFIG" >&2; exit 1; }

STAMP="$(date +%Y%m%d-%H%M%S)"
for suffix in "" "-scratch" "-local"; do
    dir="${RUN_DIR}${suffix}"
    if [ -e "$dir" ]; then
        mv "$dir" "${dir}-${STAMP}" && echo "[rerun] archived $(basename "$dir") -> $(basename "${dir}-${STAMP}")"
    fi
done

echo "[rerun] starting $CONFIG"
echo
bash "$REPO/cluster/submit_hydroflow_opt.sh" "$CONFIG"
STATUS=$?

# The first line of a stage log is the exact command that ran, which is the one
# thing worth seeing immediately when a candidate failed.
echo
for candidate in "${RUN_DIR}-local"/*/; do
    [ -d "$candidate" ] || continue
    for log in "$candidate"logs/*.log; do
        [ -f "$log" ] || continue
        echo "[rerun] ${log#"${RUN_DIR}-local/"} ($(wc -l < "$log") lines)"
        head -1 "$log" | cut -c1-200 | sed 's/^/[rerun]   /'
    done
done

echo
echo "[rerun] results:  $RUN_DIR"
echo "[rerun] stage logs and case directories: ${RUN_DIR}-local"
exit $STATUS
