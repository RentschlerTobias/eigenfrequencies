#!/usr/bin/env python3
"""Summarize a hydroflow-opt run and refuse to call a frozen metric a result.

    python3 cluster/summarize_run.py RUN_DIR [RUN_DIR ...]

Reads ``results.jsonl`` and prints, per metric, how many *distinct* values the
run produced. A metric that took one value across every candidate did not
converge — it never varied. That is exactly what happened in runs
6039132/6039133, where a stale OpenFOAM case made ``eta`` constant while the
optimizer kept happily reporting progress, and it is the check that exposed it.

Exit code 0 only if every evaluated metric varied and no candidate failed;
1 otherwise. Run it before putting any number of this run in a talk.

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


def _load(run_dir: Path) -> list[dict]:
    """Read results.jsonl, skipping blank lines."""
    path = run_dir / "results.jsonl"
    if not path.is_file():
        raise SystemExit(f"no results.jsonl in {run_dir}")
    records = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            records.append(json.loads(line))
    return records


def summarize(run_dir: Path) -> bool:
    """Print the summary for one run. Returns True if it passes the gate."""
    records = _load(run_dir)
    ok = [r for r in records if r.get("status") == "success"]
    failed = [r for r in records if r.get("status") != "success"]

    print(f"\n=== {run_dir} ===")
    print(f"evaluations: {len(records)}  success: {len(ok)}  failed: {len(failed)}")

    passed = True
    if failed:
        passed = False
        print("\nfailures (first 5):")
        for record in failed[:5]:
            print(f"  {record.get('candidate_id')}: {record.get('error')}")

    if not ok:
        print("\nnothing succeeded — no metric to check.")
        return False

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

    return passed


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        print(__doc__.strip().splitlines()[2].strip(), file=sys.stderr)
        return 2

    passed = True
    for name in args:
        passed &= summarize(Path(name))

    print("\nGATE:", "pass" if passed else "FAIL — do not present these numbers")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
