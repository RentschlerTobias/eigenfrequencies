"""Read steady-CFD hydraulic objectives from an OpenFOAM case (efficiency, cavitation, head).

Ported from the de_framework reference (tistos_files/tistosPyBib.py:ReadResults),
which used pyDtOO developing-quantity helpers. Here it is reimplemented with a
plain OpenFOAM `postProcessing` reader so it has no pyDtOO/dolfinx dependency and
runs in the dtOO + OpenFOAM environment next to `simpleFoam`.

Physical definitions (mirrors the reference):
    P    = moment_z * omega                         (shaft power)
    dH   = (ptot_out - ptot_in) / g                 (head)
    eta  = P / (rho * g * dH * Q)                    (efficiency)
    Vcav = cavitation volume from the cavitationVolume function object

NOTE (cluster validation): the exact column layout of OpenFOAM functionObject
.dat files depends on the case's `system/` setup. The column indices below match
the de_framework tistos case; confirm them against a real postProcessing/ dump on
the cluster (see HANDOFF.md) before trusting magnitudes.
"""

import os
import numpy as np


def _last_data_row(dat_path: str) -> list:
    """Return the numeric fields of the last non-comment line of an OpenFOAM .dat."""
    if not os.path.isfile(dat_path):
        raise FileNotFoundError(dat_path)
    last = None
    with open(dat_path) as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            last = line
    if last is None:
        raise ValueError(f"no data rows in {dat_path}")
    # OpenFOAM wraps vectors/tensors in parentheses; strip them to flat floats.
    cleaned = last.replace("(", " ").replace(")", " ")
    return [float(tok) for tok in cleaned.split()]


def _scalar(case_dir: str, name: str, time: str, col: int = 1) -> float:
    """Read a single scalar functionObject result (time in col 0, value in col)."""
    path = os.path.join(case_dir, "postProcessing", name, time, f"{name}.dat")
    if not os.path.isfile(path):
        # OpenFOAM sometimes names the file 'surfaceFieldValue.dat' etc.; fall back
        # to the first .dat in the time directory.
        tdir = os.path.join(case_dir, "postProcessing", name, time)
        cands = [f for f in os.listdir(tdir)] if os.path.isdir(tdir) else []
        dats = [f for f in cands if f.endswith(".dat")]
        if not dats:
            raise FileNotFoundError(path)
        path = os.path.join(tdir, dats[0])
    return _last_data_row(path)[col]


def evaluate_cfd(case_dir: str, cfd_cfg) -> dict:
    """Compute {eta, vcav, dH, P, Q, ok} from an OpenFOAM postProcessing tree.

    Args:
        case_dir: OpenFOAM case directory (contains postProcessing/)
        cfd_cfg: CFDConfig (omega, rho, g, design_head, operating_point, end_time)

    Returns dict with ok=False (+ "error") on any read/validity failure so the
    optimizer can apply a failure penalty rather than crash.
    """
    t = str(cfd_cfg.end_time)
    try:
        Q = abs(_scalar(case_dir, "Q_ru_in", t))
        ptot_in = _scalar(case_dir, "ptot_ru_in", t)
        ptot_out = _scalar(case_dir, "ptot_ru_out", t)
        # forces function object: moment is the last 3 of the flattened row;
        # take the axial (z) component as the runner torque.
        forces_row = _last_data_row(
            os.path.join(case_dir, "postProcessing", "forces", t, "forces.dat")
        )
        moment_z = forces_row[-1]
        vcav = abs(_scalar(case_dir, "V_CAV", t))

        P = moment_z * cfd_cfg.omega
        dH = (ptot_out - ptot_in) / cfd_cfg.g
        denom = cfd_cfg.rho * cfd_cfg.g * dH * Q
        eta = P / denom if denom != 0 else 0.0

        # validity: |eta| > 1 means the machine ran as a pump -> reject (reference rule)
        if abs(eta) > 1.0:
            return {"ok": False, "error": "Pump detected (|eta|>1)",
                    "eta": eta, "vcav": vcav, "dH": dH, "P": P, "Q": Q}

        return {"ok": True, "eta": float(eta), "vcav": float(vcav),
                "dH": float(dH), "P": float(P), "Q": float(Q)}
    except Exception as exc:  # noqa: BLE001 - report to optimizer, never crash the loop
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}",
                "eta": 0.0, "vcav": 0.0, "dH": 0.0, "P": 0.0, "Q": 0.0}
