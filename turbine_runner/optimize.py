#!/usr/bin/env python3
"""STAGE 3: resonance-avoidance optimization (runs on the HOST).

Orchestrates dtOO (native) + FEniCSx (enroot container) per evaluation:

    design x  --(design.json)-->  [dtOO native]     -->  runner.msh
    runner.msh                --> [fenicsx enroot]  -->  frequencies
    frequencies               --> penalty (forbidden band)

scipy.optimize.minimize drives the dtOO design parameters so that no eigenfrequency
stays inside the forbidden band [f_min, f_max].

Requirements: python3 with numpy + scipy, source ~/pe, and enroot container
`pyxis_fenicsx` imported from docker://dolfinx/dolfinx:stable.
"""

import json
import os
import subprocess
import sys

import numpy as np
from scipy.optimize import minimize

from config import DesignConfig, OptimizationConfig
from optimization import compute_penalty, band_report

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
DATA = os.path.join(HERE, "data")

FENICSX_CONTAINER = os.environ.get("FENICSX_CONTAINER", "pyxis_fenicsx")

DTOO_FAIL_PENALTY = 1e6  # returned when a design fails to build/mesh/solve


def _worker_dir(worker_id: int) -> str:
    """Return the worker-specific working directory ($TMPDIR/worker_{id})."""
    tmpdir = os.environ.get("TMPDIR", "/tmp")
    return os.path.join(tmpdir, f"worker_{worker_id}")


def _run_dtoo(design: dict, worker_id: int = 0) -> bool:
    """Write design.json and build runner.msh via the dtOO container."""
    wdir = _worker_dir(worker_id)
    os.makedirs(wdir, exist_ok=True)
    design_json = os.path.join(wdir, "design.json")
    msh = os.path.join(wdir, "runner.msh")

    with open(design_json, "w") as fh:
        json.dump(design, fh)
    # remove stale mesh so a failed build cannot be mistaken for success
    if os.path.exists(msh):
        os.remove(msh)

    cmd = [
        "bash", "-lc",
        f"source ~/pe && "
        f"export LD_LIBRARY_PATH=~/dtOO/install/lib:~/dtOO/install/lib64:$LD_LIBRARY_PATH && "
        f"export DTOO_CASE_DIR=~/dtOO/build/test/tistos && "
        f"export DTOO_OUTPUT_MSH={msh} && "
        f"export DTOO_DESIGN_JSON={design_json} && "
        f"python3 {os.path.join(HERE, 'dtoo_export.py')}",
    ]
    log_path = os.path.join(wdir, "dtoo.log")
    with open(log_path, "w") as log_fh:
        res = subprocess.run(cmd, stdout=log_fh, stderr=subprocess.STDOUT)
    if res.returncode != 0 or not os.path.exists(msh):
        with open(log_path) as log_fh:
            tail = log_fh.read()[-1600:]
        sys.stderr.write(f"[optimize] dtOO build FAILED (worker {worker_id}):\n{tail}\n")
        return False
    return True


def _run_fenicsx(worker_id: int = 0) -> dict:
    """Run evaluate.py in the fenicsx container, parse the RESULT_JSON line."""
    wdir = _worker_dir(worker_id)
    msh = os.path.join(wdir, "runner.msh")
    cmd = [
        "enroot", "start",
        "-m", f"{REPO}:/workspace",
        "-m", f"{wdir}:/worker_data",
        FENICSX_CONTAINER,
        "bash", "-c",
        # XDG_RUNTIME_DIR/TMPDIR -> container /tmp so PMIx/MPI (DOLFINx) does not
        # fall back to /run/user/$UID, which is unwritable in the batch context
        # of the head node (uc2n601) and made all its workers fail modal solve.
        "export HOME=/tmp; export DOLFINX_CACHE_DIR=/tmp; "
        "export XDG_RUNTIME_DIR=/tmp; export TMPDIR=/tmp; "
        f"python3 /workspace/turbine_runner/evaluate.py /worker_data/runner.msh",
    ]
    log_path = os.path.join(wdir, "fenicsx.log")
    with open(log_path, "w") as log_fh:
        res = subprocess.run(cmd, stdout=log_fh, stderr=subprocess.STDOUT)
    with open(log_path) as log_fh:
        log_lines = log_fh.read().splitlines()
    for line in reversed(log_lines):
        if line.startswith("RESULT_JSON "):
            return json.loads(line[len("RESULT_JSON "):])
    sys.stderr.write(f"[optimize] fenicsx eval FAILED (worker {worker_id}):\n{log_lines[-40:]}\n")
    return {"frequencies_hz": [], "ok": False}


def main() -> None:
    design_cfg = DesignConfig()
    opt_cfg = OptimizationConfig()
    # Optional env overrides (handy for short smoke runs without editing config).
    opt_cfg.max_iter = int(os.environ.get("OPT_MAX_ITER", opt_cfg.max_iter))
    opt_cfg.f_min = float(os.environ.get("OPT_FMIN", opt_cfg.f_min))
    opt_cfg.f_max = float(os.environ.get("OPT_FMAX", opt_cfg.f_max))
    labels = design_cfg.labels
    x0 = np.array(design_cfg.x0)
    bounds = design_cfg.bounds

    print("=" * 60)
    print("Runner resonance-avoidance optimization")
    print("=" * 60)
    print(f"Design params: {labels}")
    print(f"Forbidden band: [{opt_cfg.f_min}, {opt_cfg.f_max}] Hz")
    print(f"Method: {opt_cfg.method}, max_iter={opt_cfg.max_iter}")
    print()

    history = []

    def objective(x):
        design = {lab: float(v) for lab, v in zip(labels, x)}
        if not _run_dtoo(design):
            history.append({"x": list(x), "penalty": DTOO_FAIL_PENALTY, "freqs": []})
            return DTOO_FAIL_PENALTY
        result = _run_fenicsx()
        if not result.get("ok"):
            history.append({"x": list(x), "penalty": DTOO_FAIL_PENALTY, "freqs": []})
            return DTOO_FAIL_PENALTY
        freqs = result["frequencies_hz"]
        penalty = compute_penalty(freqs, opt_cfg)
        history.append({"x": list(x), "penalty": penalty, "freqs": freqs})
        print(f"[eval {len(history)}] penalty={penalty:.4g}  {band_report(freqs, opt_cfg)}")
        return penalty

    res = minimize(
        objective, x0, method=opt_cfg.method, bounds=bounds,
        options={"maxiter": opt_cfg.max_iter, "disp": True},
    )

    best = {lab: float(v) for lab, v in zip(labels, res.x)}
    print()
    print("=" * 60)
    print("Optimization finished")
    print(f"Best design: {best}")
    print(f"Best penalty: {res.fun:.4g}")
    out = {"best_design": best, "best_penalty": float(res.fun), "history": history}
    out_path = os.path.join(HERE, "output", "optimization.json")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w") as fh:
        json.dump(out, fh, indent=2)
    print(f"History written to: {out_path}")


if __name__ == "__main__":
    main()
