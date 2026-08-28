"""Evaluate one hydroflow-opt candidate: request.json -> physics -> result.json.

Invoked by hydroflow-opt's SubprocessBackend through the command built in
:meth:`eigenfrequencies.hydroflow.case.MachineCasePlugin.worker_command`::

    python -m eigenfrequencies.hydroflow.worker --machine NAME REQUEST RESULT

Contract (.omo/notes/hydroflow-contract.md):

* request carries ``candidate.id`` and ``candidate.parameters`` (name -> value),
  the ``[case.options]`` table as ``case.options``, and a ``context`` block whose
  ``scratch_dir`` is reserved for this one candidate
* result must echo it as ``candidate_id`` — a mismatch is scored as failed
* ``status`` is "success" or "failed", ``objective`` a float or null,
  ``metadata`` an object (never a scalar), ``error`` a string or null
* the process must exit 0 and leave a result file behind **even when the
  evaluation fails**. An unwritten result is an unexplained failure for the
  orchestrator, so every path here ends in :func:`_write`.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import traceback
from pathlib import Path
from typing import Any

_STAGE_MESH = "mesh"
_STAGE_MODAL = "modal"
_STAGE_CFD = "cfd"


def _write(result_path: Path, payload: dict[str, Any]) -> None:
    """Write result.json, creating the parent directory if needed."""
    result_path.parent.mkdir(parents=True, exist_ok=True)
    result_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _failed(
    result_path: Path,
    candidate_id: Any,
    error: str,
    *,
    timings: dict[str, float] | None = None,
    metadata: dict[str, Any] | None = None,
) -> int:
    """Record a failed evaluation and exit 0 — the run itself did not crash."""
    _write(
        result_path,
        {
            "candidate_id": candidate_id,
            "status": "failed",
            "objective": None,
            "timings": timings or {},
            "metadata": metadata or {},
            "error": error,
        },
    )
    return 0


def _override(cfg: Any, values: dict[str, Any], *, section: str) -> None:
    """Apply ``[case.options.<section>]`` onto a config dataclass, strictly.

    A key the dataclass does not declare is an error, not a no-op. Silently
    dropping ``w_resonanc`` would leave a run that looks healthy, finishes, and
    is quietly incomparable to the other two — the failure mode this project
    has already paid for once.

    ``[case.options.cfd]`` is the exception: it is read twice, once here for
    the operating point and once by the CFD stage for its plumbing. Those keys
    are skipped rather than rejected.
    """
    from eigenfrequencies.hydroflow.physics import CFD_STAGE_KEYS

    foreign = CFD_STAGE_KEYS if section == "cfd" else frozenset()
    for field, value in values.items():
        if field in foreign:
            continue
        if not hasattr(cfg, field):
            known = sorted(vars(cfg))
            raise ValueError(
                f"options.{section} has no field {field!r}; known: {', '.join(known)}"
            )
        setattr(cfg, field, value)


def evaluate(
    machine: str,
    parameters: dict[str, float],
    options: dict[str, Any],
    context: dict[str, Any] | None = None,
) -> tuple:
    """Run the physics for one design.

    Args:
        machine: machine name, resolved to a catalog YAML.
        parameters: candidate design vector.
        options: the ``case.options`` table from the request.
        context: the request's ``context`` block. Carries ``scratch_dir`` — the
            directory hydroflow-opt reserved for *this* candidate — and the
            resource budget, so it decides where the evaluation runs and with
            how many ranks.

    Returns ``(objective, timings, metadata)``. Raises on any failure; the
    caller turns that into a failed result.
    """
    from eigenfrequencies.adapters.dtoo import load_machine_yaml
    from eigenfrequencies.adapters.dtoo.machine_yaml import machine_yaml_path
    from eigenfrequencies.config import CFDConfig, ObjectiveConfig, OptimizationConfig
    from eigenfrequencies.penalty.objective import combined_objective, resonance_term

    yaml_path = options.get("machine_yaml") or machine_yaml_path(machine)
    machine_cfg = load_machine_yaml(yaml_path)

    unknown = set(parameters) - set(machine_cfg.design)
    if unknown:
        raise ValueError(
            f"candidate carries parameters absent from {machine}: {sorted(unknown)}"
        )

    eval_mode = options.get("eval_mode", "combined")
    if eval_mode not in ("combined", "cfd_only", "resonance_only"):
        raise ValueError(f"unknown eval_mode: {eval_mode!r}")

    n_rpm = float(options.get("n_rpm", 72.0))
    cfd_cfg = CFDConfig(n_rpm=n_rpm)
    opt_cfg = OptimizationConfig(n_rpm=n_rpm)
    obj_cfg = ObjectiveConfig()
    for cfg, key in ((cfd_cfg, "cfd"), (opt_cfg, "optimization"), (obj_cfg, "objective")):
        _override(cfg, options.get(key) or {}, section=key)

    timings: dict[str, float] = {}
    metadata: dict[str, Any] = {
        "machine": machine,
        "eval_mode": eval_mode,
        "parameters": dict(parameters),
    }

    run_modal = eval_mode in ("combined", "resonance_only")
    run_cfd = eval_mode in ("combined", "cfd_only")

    frequencies = None
    if run_modal:
        from eigenfrequencies.hydroflow.physics import run_modal_stage

        frequencies, mesh_meta = run_modal_stage(machine_cfg, parameters, options, context)
        # The stage times its two halves itself; deriving one from the other
        # would report a negative duration whenever the clocks disagree.
        timings[_STAGE_MESH] = mesh_meta.pop("mesh_seconds", 0.0)
        timings[_STAGE_MODAL] = mesh_meta.pop("modal_seconds", 0.0)
        metadata["mesh"] = mesh_meta
        metadata["frequencies_hz"] = [float(f) for f in frequencies]

    cfd = None
    if run_cfd:
        from eigenfrequencies.hydroflow.physics import run_cfd_stage

        started = time.perf_counter()
        cfd = run_cfd_stage(machine_cfg, parameters, options, cfd_cfg, context)
        timings[_STAGE_CFD] = time.perf_counter() - started
        if not cfd.get("ok"):
            raise RuntimeError(f"CFD evaluation failed: {cfd.get('error')}")
        metadata["cfd"] = {k: cfd[k] for k in ("eta", "vcav", "dH", "P", "Q") if k in cfd}

    if eval_mode == "combined":
        objective, breakdown = combined_objective(
            cfd, frequencies, cfd_cfg, opt_cfg, obj_cfg
        )
        metadata["breakdown"] = breakdown
    elif eval_mode == "cfd_only":
        from eigenfrequencies.penalty.objective import cfd_scalar

        objective = cfd_scalar(cfd, cfd_cfg, obj_cfg)
    else:
        objective = resonance_term(frequencies, opt_cfg, obj_cfg)

    return float(objective), timings, metadata


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="eigenfrequencies.hydroflow.worker")
    parser.add_argument("--machine", required=True)
    parser.add_argument("request")
    parser.add_argument("result")
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])

    result_path = Path(args.result)
    candidate_id = None
    try:
        request = json.loads(Path(args.request).read_text(encoding="utf-8"))
        candidate = request["candidate"]
        candidate_id = candidate["id"]
        parameters = {str(k): float(v) for k, v in candidate["parameters"].items()}
        # The orchestrator nests the case table: request.case.options, not
        # request.options (runner.py:69-82). Reading the wrong key silently
        # discards every setting from [case.options].
        options = (request.get("case") or {}).get("options") or {}
        context = request.get("context") or {}
    except Exception as exc:  # noqa: BLE001 - a malformed request is still a result
        return _failed(result_path, candidate_id, f"{type(exc).__name__}: {exc}")

    started = time.perf_counter()
    try:
        objective, timings, metadata = evaluate(args.machine, parameters, options, context)
    except Exception as exc:  # noqa: BLE001 - report, never crash the optimizer
        return _failed(
            result_path,
            candidate_id,
            f"{type(exc).__name__}: {exc}",
            timings={"total": time.perf_counter() - started},
            metadata={"traceback": traceback.format_exc(limit=8)},
        )

    timings["total"] = time.perf_counter() - started
    _write(
        result_path,
        {
            "candidate_id": candidate_id,
            "status": "success",
            "objective": objective,
            "timings": timings,
            "metadata": metadata,
            "error": None,
        },
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
