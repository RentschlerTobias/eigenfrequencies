#!/usr/bin/env python3
"""STAGE 3: resonance-avoidance optimization (runs on the HOST).

Orchestrates the two containers per evaluation (Option A, host orchestration):

    design x  --(design.json)-->  [dtOO container]  -->  runner.msh
    runner.msh                --> [fenicsx container] -->  frequencies
    frequencies               --> penalty (forbidden band)

scipy.optimize.minimize drives the dtOO design parameters so that no eigenfrequency
stays inside the forbidden band [f_min, f_max].

Requirements on the host: python3 with numpy + scipy, and docker with the images
`atismer/dtoo-opensuse:stable` and `eigenfrequencies-fenicsx:latest`.

This is expensive: each evaluation runs a full dtOO geometry build + mesh + a FEM
solve (minutes). Keep OptimizationConfig.max_iter modest.
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

DTOO_IMAGE = os.environ.get("DTOO_IMAGE", "atismer/dtoo-opensuse:stable")
FENICSX_IMAGE = os.environ.get("FENICSX_IMAGE", "eigenfrequencies-fenicsx:latest")

DTOO_FAIL_PENALTY = 1e6  # returned when a design fails to build/mesh/solve


def _run_dtoo(design: dict) -> bool:
    """Write design.json and build runner.msh via the dtOO container."""
    os.makedirs(DATA, exist_ok=True)
    with open(os.path.join(DATA, "design.json"), "w") as fh:
        json.dump(design, fh)
    # remove stale mesh so a failed build cannot be mistaken for success
    msh = os.path.join(DATA, "runner.msh")
    if os.path.exists(msh):
        os.remove(msh)

    cmd = [
        "docker", "run", "--rm",
        "-v", f"{DATA}:/work",
        "-v", f"{HERE}:/src",
        "-w", "/dtOO/test/tistos",
        DTOO_IMAGE,
        "bash", "-lc",
        "export LD_LIBRARY_PATH=/dtOO-install/lib:/dtOO-install/lib64:$LD_LIBRARY_PATH "
        "&& python3.12 /src/dtoo_export.py",
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0 or not os.path.exists(msh):
        sys.stderr.write(f"[optimize] dtOO build FAILED:\n{res.stdout[-800:]}\n{res.stderr[-800:]}\n")
        return False
    return True


def _run_fenicsx() -> dict:
    """Run evaluate.py in the fenicsx container, parse the RESULT_JSON line."""
    cmd = [
        "docker", "run", "--rm", "-e", "PYTHONUNBUFFERED=1",
        "-v", f"{REPO}:/workspace",
        "-w", "/workspace/turbine_runner",
        FENICSX_IMAGE,
        "python3", "evaluate.py", "/workspace/turbine_runner/data/runner.msh",
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    for line in reversed(res.stdout.splitlines()):
        if line.startswith("RESULT_JSON "):
            return json.loads(line[len("RESULT_JSON "):])
    sys.stderr.write(f"[optimize] fenicsx eval FAILED:\n{res.stdout[-800:]}\n{res.stderr[-800:]}\n")
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
