#!/usr/bin/env python3
"""Summarize a hydroflow-opt run and refuse to call a frozen metric a result.

    python3 cluster/summarize_run.py RUN_DIR [RUN_DIR ...]

Prints, per metric, how many *distinct* values the run produced. A metric that
took one value across every candidate did not converge — it never varied. That
is exactly what happened in runs 6039132/6039133, where a stale OpenFOAM case
made ``eta`` constant while the optimizer kept happily reporting progress, and
it is the check that exposed it.

Reads ``results.jsonl`` when it exists, and falls back to the per-candidate
``evaluations/*/outcome.json`` when it does not. That fallback is the normal
case, not an edge case: hydroflow-opt writes ``results.jsonl`` once, after the
whole generation loop returns, while the dev configs are designed to be killed
by the walltime and a production run only finishes on its last resume. Without
it this gate is unusable exactly when it is needed.

Exit code 0 only if every evaluated metric varied and no candidate failed;
1 otherwise. An unfinished run can still FAIL — a frozen metric is frozen at
ten candidates too — but it never reports a bare pass: the header says how many
of the expected evaluations are in, so a "pass" on 12 of 32 is visibly partial.
Run it before putting any number of this run in a talk.

Stdlib only — it runs anywhere, including a login node with no venv.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

#: Metrics worth checking: (label, path into the result record, zero_ok).
#:
#: ``zero_ok`` marks the two quantities that may legitimately be constant *at
#: zero*: the resonance penalty is a soft constraint and reads 0 whenever no
#: mode sits in the forbidden band — which is the outcome one hopes for — and a
#: design family without cavitation reports vcav = 0 throughout. Constant at any
#: other value is frozen for those too.
#:
#: ``Q`` is deliberately absent. The flow rate is set by the mapped inlet
#: profile in ``boundaryData_RU_INLET``, so it is an input to the simulation,
#: not a result: two candidates measured 17.68047 to every digit while eta,
#: vcav and dH differed by factors. Listing it here would fail every healthy
#: run.
_METRICS: tuple[tuple[str, tuple[str, ...], bool], ...] = (
    ("objective", ("objective",), False),
    ("eta", ("metadata", "cfd", "eta"), False),
    ("vcav", ("metadata", "cfd", "vcav"), True),
    ("dH", ("metadata", "cfd", "dH"), False),
    ("f_cfd", ("metadata", "breakdown", "f_cfd"), False),
    ("f_resonance", ("metadata", "breakdown", "f_resonance"), True),
    ("f_1", ("metadata", "frequencies_hz", 0), False),
)


def _dig(record: Any, path: tuple) -> Any:
    """Follow *path* through nested dicts/lists, or return None."""
    node = record
    for key in path:
        if isinstance(key, int):
            if not isinstance(node, list) or len(node) <= key:
                return None
            node = node[key]
        else:
            if not isinstance(node, dict) or key not in node:
                return None
            node = node[key]
    return node


def _load(run_dir: Path) -> tuple[list[dict], str]:
    """Read the run's evaluation records. Returns ``(records, source)``.

    ``results.jsonl`` is authoritative but written only once, after the last
    generation, so it is absent for every run that is still going or that a
    walltime killed. The per-candidate ``evaluations/*/outcome.json`` files are
    written as each candidate completes and carry the identical shape — the
    orchestrator serializes both through the same function — so the metric paths
    below need no special casing.
    """
    path = run_dir / "results.jsonl"
    if path.is_file():
        records = []
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                records.append(json.loads(line))
        return records, "results.jsonl"

    # Sorted by name: the candidate ids are zero-padded
    # (island-000-generation-000001-trial-002), so lexical order is island,
    # then generation, then position. glob() alone returns directory order.
    #
    # evaluations/*/outcome.json and not **/outcome.json: a re-evaluated
    # candidate keeps its superseded runs under evaluations/<id>/attempts/,
    # and counting those would report stale numbers as if they were results.
    outcomes = sorted((run_dir / "evaluations").glob("*/outcome.json"))
    if not outcomes:
        raise SystemExit(
            f"no evaluations found in {run_dir}: neither results.jsonl "
            f"nor evaluations/*/outcome.json"
        )
    records = []
    for outcome in outcomes:
        try:
            records.append(json.loads(outcome.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError) as exc:
            # A candidate whose outcome is being written right now, or a
            # truncated file from a killed job. Skipping it loses one data
            # point; aborting would lose the whole summary.
            print(f"  skipped unreadable {outcome.parent.name}/outcome.json: {exc}")
    return records, "evaluations/*/outcome.json"


def _expected_total(run_dir: Path) -> tuple[int | None, str | None]:
    """Expected evaluation count and run status from manifest.json.

    Both are best effort: the manifest is what tells a partial run from a
    finished one, but a run directory without it is still worth summarizing.
    """
    try:
        manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None, None
    status = manifest.get("status")
    opt = (manifest.get("config") or {}).get("optimization") or {}
    try:
        # The initial population counts as its own round, hence generations + 1.
        total = int(opt["islands"]) * int(opt["population_size"]) * (
            int(opt["generations"]) + 1
        )
    except (KeyError, TypeError, ValueError):
        return None, status
    return total, status


def summarize(run_dir: Path) -> tuple[bool, bool]:
    """Print the summary for one run. Returns ``(passes_gate, is_partial)``.

    The two are separate on purpose. A frozen metric is a hard failure whether
    or not the run finished, so a partial run must be able to FAIL. But a
    partial run that looks healthy must not be reported as a clean pass either,
    and forcing an exit code of 1 on it would make the exit code useless for
    watching a run that is doing fine — which is what it is mostly used for.
    """
    print(f"\n=== {run_dir} ===")
    records, source = _load(run_dir)
    expected, status = _expected_total(run_dir)
    ok = [r for r in records if r.get("status") == "success"]
    failed = [r for r in records if r.get("status") != "success"]

    progress = f"evaluations: {len(records)}"
    if expected:
        progress += f" of {expected} expected"
    print(f"{progress}  success: {len(ok)}  failed: {len(failed)}")
    print(f"source: {source}  run status: {status or 'unknown'}")

    # A run still in progress is not a result. Say so next to the numbers
    # rather than only in the gate line, because these numbers get copied out
    # of this output and into slides.
    #
    # results.jsonl is itself the proof of a finished run — the orchestrator
    # writes it only after the generation loop returns — so its presence
    # settles the question even for a `run`-mode config, which has no manifest.
    # The expected count stays progress information and is deliberately not
    # used to judge finishedness: it is derived from the config, and a run that
    # legitimately evaluates a different number would be branded unfinished
    # forever.
    partial = source != "results.jsonl" and status != "complete"
    if partial:
        print("PARTIAL RUN — these numbers are a progress check, not a result.")

    passed = True
    if failed:
        passed = False
        print("\nfailures (first 5):")
        for record in failed[:5]:
            print(f"  {record.get('candidate_id')}: {record.get('error')}")

    if not ok:
        print("\nnothing succeeded — no metric to check.")
        return False, partial

    print(f"\n{'metric':<14}{'n':>6}{'unique':>8}{'min':>14}{'max':>14}")
    for label, path, zero_ok in _METRICS:
        values = [_dig(r, path) for r in ok]
        values = [float(v) for v in values if isinstance(v, (int, float))]
        if not values:
            continue  # not part of this eval_mode
        unique = len(set(values))
        flag = ""
        if unique == 1:
            if zero_ok and values[0] == 0.0:
                # Inactive, not frozen: the constraint never bit.
                flag = "  (inactive)"
            else:
                # One value over the whole run: frozen, not converged.
                flag = "  <-- FROZEN"
                passed = False
        print(
            f"{label:<14}{len(values):>6}{unique:>8}"
            f"{min(values):>14.6g}{max(values):>14.6g}{flag}"
        )

    best = min(ok, key=lambda r: r.get("objective", float("inf")))
    print(f"\nbest objective: {best.get('objective'):.6g}  ({best.get('candidate_id')})")

    timings: dict[str, list[float]] = {}
    for record in ok:
        for stage, seconds in (record.get("timings") or {}).items():
            timings.setdefault(stage, []).append(float(seconds))
    if timings:
        print("\nmean seconds per stage:")
        for stage, seconds in sorted(timings.items()):
            print(f"  {stage:<10}{sum(seconds) / len(seconds):>10.1f}")

    return passed, partial


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        print(__doc__.strip().splitlines()[2].strip(), file=sys.stderr)
        return 2

    passed = True
    partial = False
    for name in args:
        run_passed, run_partial = summarize(Path(name))
        passed &= run_passed
        partial |= run_partial

    if not passed:
        verdict = "FAIL — do not present these numbers"
    elif partial:
        verdict = "no failure yet — but the run is unfinished, not a result"
    else:
        verdict = "pass"
    print("\nGATE:", verdict)
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
