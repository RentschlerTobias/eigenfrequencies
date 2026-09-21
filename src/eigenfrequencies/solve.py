"""Thin command-line entry point for a single modal analysis + penalty run.

Usage::

    python -m eigenfrequencies.solve --msh runner.msh --machine tistos \
        --set n_rpm=72 --result result.json

Either ``--config <yaml>`` (a full ``ModalAnalysisConfig``) or ``--machine``
(a preset, optionally with ``--set`` overrides) selects the configuration.
The result is written as JSON to ``--result`` and, with ``--stdout``, printed.
"""

import argparse
import json
import sys
from typing import Any, List, Optional

from eigenfrequencies.api import solve_modal


def _coerce(value: str) -> Any:
    for cast in (int, float):
        try:
            return cast(value)
        except ValueError:
            pass
    return value


def _parse_overrides(items: Optional[List[str]]) -> dict:
    overrides: dict = {}
    for item in items or []:
        key, sep, value = item.partition("=")
        if not sep:
            raise SystemExit(f"--set expects KEY=VALUE, got {item!r}")
        overrides[key] = _coerce(value)
    return overrides


def _build_config(args):
    if args.config:
        from eigenfrequencies.config_yaml import load_config

        if args.set:
            raise SystemExit("--set cannot be combined with --config")
        return load_config(args.config)

    from eigenfrequencies.api import load_preset

    if not args.machine:
        raise SystemExit("either --config or --machine is required")
    overrides = _parse_overrides(args.set)
    if args.n_rpm is not None:
        overrides["n_rpm"] = args.n_rpm
    if "n_rpm" not in overrides:
        raise SystemExit("n_rpm is required (use --n-rpm or --set n_rpm=VALUE)")
    return load_preset(args.machine, overrides)


def _payload(result) -> dict:
    return {
        "frequencies_hz": list(result.frequencies_hz),
        "resonance_penalty": result.resonance_penalty,
        "violating_modes": list(result.violating_modes),
        "band_report": result.band_report,
        "metadata": result.metadata,
    }


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="eigenfrequencies.solve",
        description="Modal analysis + resonance penalty for one mesh.",
    )
    parser.add_argument("--msh", required=True, help="structural-mechanics .msh")
    parser.add_argument("--config", help="full ModalAnalysisConfig YAML")
    parser.add_argument("--machine", help="machine preset name (e.g. tistos)")
    parser.add_argument("--n-rpm", dest="n_rpm", type=float, help="rotational speed")
    parser.add_argument(
        "--set", action="append", metavar="KEY=VALUE", help="resonance override"
    )
    parser.add_argument("--result", help="write JSON result to this path")
    parser.add_argument("--stdout", action="store_true", help="print JSON to stdout")
    args = parser.parse_args(argv)

    try:
        config = _build_config(args)
        payload = _payload(solve_modal(args.msh, config))
    except Exception as exc:  # noqa: BLE001 - surface any failure as JSON
        error = {"error": f"{type(exc).__name__}: {exc}"}
        if args.result:
            with open(args.result, "w", encoding="utf-8") as handle:
                json.dump(error, handle, indent=2)
        if args.stdout:
            print(json.dumps(error, indent=2))
        return 1

    text = json.dumps(payload, indent=2)
    if args.result:
        with open(args.result, "w", encoding="utf-8") as handle:
            handle.write(text)
    if args.stdout or not args.result:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
