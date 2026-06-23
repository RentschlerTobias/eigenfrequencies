"""Combined CFD + resonance objective for the multi-objective runner optimization.

Scalarizes the three classic hydraulic objectives (efficiency, cavitation volume,
design head) and adds the structural-resonance penalty as a constraint term
(decision (a): constraint/penalty, not a separate Pareto axis).

Dependency-light (numpy only, plus optimization.compute_penalty) so it imports on
the host optimizer side without dolfinx. The CFD scalarization mirrors the
de_framework reference (tistos_files/tistosPyBib.py:GiveFitness):

    f_cfd = w_eta*tanh(|1+eta|) + w_cav*tanh(Vcav*1e6) + w_head*tanh(|dH - dH_zul|)

Lower is better (minimization, matching Differential Evolution / Nelder-Mead).
"""

import numpy as np

from optimization import compute_penalty, band_report


def cfd_scalar(cfd: dict, cfd_cfg, obj_cfg) -> float:
    """Scalarize the three hydraulic objectives into one (lower = better).

    Args:
        cfd: {"eta", "vcav", "dH", ...} from cfd_eval.evaluate_cfd
        cfd_cfg: CFDConfig (design_head target)
        obj_cfg: ObjectiveConfig (weights)
    """
    eta = float(cfd["eta"])
    vcav = float(cfd["vcav"])
    dH = float(cfd["dH"])

    eta_term = abs(1.0 + eta)               # eta ~ -1 for a good turbine -> term -> 0
    cav_term = vcav * 1e6                    # scale up tiny cavitation volumes
    head_term = abs(dH - cfd_cfg.design_head)

    return (
        obj_cfg.w_eta * np.tanh(eta_term)
        + obj_cfg.w_cav * np.tanh(cav_term)
        + obj_cfg.w_head * np.tanh(head_term)
    )


def resonance_term(frequencies, opt_cfg, obj_cfg) -> float:
    """Resonance penalty as a constraint term (0 unless a mode is in the band)."""
    penalty = compute_penalty(frequencies, opt_cfg)
    if obj_cfg.mode == "hard":
        return obj_cfg.hard_penalty * penalty if penalty > 0 else 0.0
    return obj_cfg.w_resonance * penalty


def combined_objective(cfd, frequencies, cfd_cfg, opt_cfg, obj_cfg) -> tuple:
    """Full objective = hydraulic scalar + resonance constraint term.

    Returns:
        (total, breakdown) where breakdown logs each component for the report.
    """
    f_cfd = cfd_scalar(cfd, cfd_cfg, obj_cfg)
    f_res = resonance_term(frequencies, opt_cfg, obj_cfg)
    total = float(f_cfd + f_res)
    breakdown = {
        "total": total,
        "f_cfd": float(f_cfd),
        "f_resonance": float(f_res),
        "eta": float(cfd["eta"]),
        "vcav": float(cfd["vcav"]),
        "dH": float(cfd["dH"]),
        "resonance": band_report(frequencies, opt_cfg),
    }
    return total, breakdown
