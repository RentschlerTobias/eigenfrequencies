#!/usr/bin/env python3
"""Multi-objective driver: hydraulic CFD objectives + structural resonance penalty.

Per design x:
    x --dtOO--> OF case dir  --simpleFoam--> eta, Vcav, dH   (cfd_eval)
            \\-> runner.msh    --modal solve-> eigenfrequencies (evaluate.py)
    objective = combined_objective(cfd, freqs)   # CFD scalar + resonance constraint

This is the host-orchestration variant of optimize.py extended with the CFD
objectives. It reuses optimize._run_dtoo / optimize._run_fenicsx for the two
containers and adds the CFD read-back via cfd_eval.

CFD is OPTIONAL here: if no OpenFOAM case dir is available (e.g. local box without
simpleFoam), set CFD_CASE_DIR="" and the run degrades to the resonance-only
objective, so the wiring stays testable. On the cluster the CFD step produces the
case dir; see HANDOFF.md.
"""

import json
import os

import numpy as np
from scipy.optimize import minimize

from config import (
    DesignConfig, OptimizationConfig, CFDConfig, ObjectiveConfig,
)
from objective import combined_objective, resonance_term
from cfd_eval import evaluate_cfd
from optimize import _run_dtoo, _run_fenicsx, DTOO_FAIL_PENALTY, HERE

CFD_CASE_DIR = os.environ.get("CFD_CASE_DIR", os.path.join(HERE, "data", "of_case"))


def _evaluate_design(x, labels, cfd_cfg, opt_cfg, obj_cfg):
    """One full evaluation: dtOO -> (CFD + modal) -> combined objective."""
    design = {lab: float(v) for lab, v in zip(labels, x)}
    if not _run_dtoo(design):
        return DTOO_FAIL_PENALTY, {"error": "dtoo_build_failed"}

    fre = _run_fenicsx()
    if not fre.get("ok"):
        return DTOO_FAIL_PENALTY, {"error": "modal_solve_failed"}
    freqs = fre["frequencies_hz"]

    # CFD objectives are optional; degrade to resonance-only if no case dir present.
    if CFD_CASE_DIR and os.path.isdir(CFD_CASE_DIR):
        cfd = evaluate_cfd(CFD_CASE_DIR, cfd_cfg)
        if not cfd.get("ok"):
            return DTOO_FAIL_PENALTY, {"error": f"cfd_failed: {cfd.get('error')}"}
        total, breakdown = combined_objective(cfd, freqs, cfd_cfg, opt_cfg, obj_cfg)
        return total, breakdown

    f_res = resonance_term(freqs, opt_cfg, obj_cfg)
    return float(f_res), {"total": float(f_res), "f_cfd": None,
                          "f_resonance": float(f_res), "freqs": freqs,
                          "note": "CFD skipped (no case dir) - resonance only"}


def main() -> None:
    design_cfg = DesignConfig()
    opt_cfg = OptimizationConfig()
    cfd_cfg = CFDConfig()
    obj_cfg = ObjectiveConfig()

    opt_cfg.max_iter = int(os.environ.get("OPT_MAX_ITER", opt_cfg.max_iter))
    opt_cfg.f_min = float(os.environ.get("OPT_FMIN", opt_cfg.f_min))
    opt_cfg.f_max = float(os.environ.get("OPT_FMAX", opt_cfg.f_max))

    labels = design_cfg.labels
    x0 = np.array(design_cfg.x0)
    bounds = design_cfg.bounds

    print("=" * 60)
    print("Runner CFD + resonance multi-objective optimization")
    print("=" * 60)
    print(f"Design params : {labels}")
    print(f"Forbidden band: [{opt_cfg.f_min}, {opt_cfg.f_max}] Hz")
    print(f"CFD case dir  : {CFD_CASE_DIR or '(none -> resonance-only)'}")
    print(f"Weights       : eta={obj_cfg.w_eta} cav={obj_cfg.w_cav} "
          f"head={obj_cfg.w_head} resonance={obj_cfg.w_resonance}")
    print()

    history = []

    def objective(x):
        total, breakdown = _evaluate_design(x, labels, cfd_cfg, opt_cfg, obj_cfg)
        history.append({"x": list(map(float, x)), **breakdown})
        print(f"[eval {len(history)}] objective={total:.4g}  {breakdown}")
        return total

    res = minimize(
        objective, x0, method=opt_cfg.method, bounds=bounds,
        options={"maxiter": opt_cfg.max_iter, "disp": True},
    )

    best = {lab: float(v) for lab, v in zip(labels, res.x)}
    out = {"best_design": best, "best_objective": float(res.fun), "history": history}
    out_path = os.path.join(HERE, "output", "optimization_multi.json")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w") as fh:
        json.dump(out, fh, indent=2)
    print("\n" + "=" * 60)
    print(f"Best design   : {best}")
    print(f"Best objective: {res.fun:.4g}")
    print(f"History       : {out_path}")


if __name__ == "__main__":
    main()
