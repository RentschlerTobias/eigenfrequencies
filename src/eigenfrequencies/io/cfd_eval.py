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

Column layout verified 2026-08-28 against the case definition in
rl_framework/xml/tistos_ru_of.xml and the reference reader
rl_framework/tistos_files/tistosPyBib.py:ReadResults:

  Q_ru_in / ptot_ru_in / ptot_ru_out  surfaceFieldValue, operation sum,
                                      writeFields no -> [time, value], col 1
  V_CAV                               cavitationVolume, operation sum -> col 1
  forces (moment.dat)                 type forces, libforces.so, patches
                                      (RU_BLADE), CofR (0 0 0), rhoInf 997
                                      -> [time, total(3), pressure(3),
                                      viscous(3)], total_z at index 3

Note rhoInf=997 in the forces functionObject against rho=1000 in tistos.yaml:
a systematic 0.3 % bias in eta. Harmless for ranking designs, worth aligning
before quoting absolute efficiencies.
"""

import os

#: Fraction of the trailing iterations averaged for every quantity. A steady
#: simpleFoam solution still oscillates, so the de_framework reference averages
#: the last tenth of the run (average_time = endTime/10) rather than reading a
#: single row. Taking one row feeds that oscillation straight into the DE
#: objective as noise.
_AVERAGE_LAST_FRACTION = 0.1


def _data_rows(dat_path: str) -> list:
    """Return all numeric rows of an OpenFOAM .dat as lists of floats."""
    if not os.path.isfile(dat_path):
        raise FileNotFoundError(dat_path)
    rows = []
    with open(dat_path) as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            # OpenFOAM wraps vectors/tensors in parentheses; strip to flat floats.
            cleaned = line.replace("(", " ").replace(")", " ")
            rows.append([float(tok) for tok in cleaned.split()])
    if not rows:
        raise ValueError(f"no data rows in {dat_path}")
    return rows


def _last_data_row(dat_path: str) -> list:
    """Return the numeric fields of the last non-comment line of an OpenFOAM .dat."""
    return _data_rows(dat_path)[-1]


def _mean_last(dat_path: str, col: int) -> float:
    """Mean of *col* over the trailing _AVERAGE_LAST_FRACTION of the rows."""
    rows = _data_rows(dat_path)
    n = max(1, int(len(rows) * _AVERAGE_LAST_FRACTION))
    tail = rows[-n:]
    return float(sum(r[col] for r in tail) / len(tail))


def _scalar_path(case_dir: str, name: str, time: str) -> str:
    """Resolve the .dat file of a scalar functionObject."""
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
    return path


def _scalar(case_dir: str, name: str, time: str, col: int = 1) -> float:
    """Trailing-average of a scalar functionObject (time in col 0, value in col)."""
    return _mean_last(_scalar_path(case_dir, name, time), col)


def _last_time(case_dir: str, name: str, time: str) -> float:
    """Last written iteration of a scalar functionObject."""
    return _last_data_row(_scalar_path(case_dir, name, time))[0]


def _moment_z(case_dir: str, folder: str) -> float:
    """Axial (z) runner torque from the forces functionObject.

    de_framework reads moment.dat and takes the z-component of the *total*
    moment. After stripping parentheses the row is
    [time, total_x, total_y, total_z, pressure_x..., viscous_x...], so total_z
    is index 3. Falls back to the combined forces.dat if moment.dat is absent.
    """
    base = os.path.join(case_dir, "postProcessing", "forces", folder)
    for fname in ("moment.dat", "moment_ru_blade.dat"):
        p = os.path.join(base, fname)
        if os.path.isfile(p):
            return _mean_last(p, 3)
    # combined forces.dat: [time, force(3), moment(3), ...] -> moment_z at index 6
    p = os.path.join(base, "forces.dat")
    if os.path.isfile(p):
        return _mean_last(p, 6)
    raise FileNotFoundError(os.path.join(base, "moment.dat"))


def evaluate_cfd(case_dir: str, cfd_cfg) -> dict:
    """Compute {eta, vcav, dH, P, Q, ok} from an OpenFOAM postProcessing tree.

    Args:
        case_dir: OpenFOAM case directory (contains postProcessing/)
        cfd_cfg: CFDConfig (omega, rho, g, design_head, operating_point,
                 post_folder). Results are read from postProcessing/<name>/<post_folder>;
                 the turbulent restart writes into the folder named by its start
                 time (de_framework uses "100"), and the last row is the endTime.

    Returns dict with ok=False (+ "error") on any read/validity failure so the
    optimizer can apply a failure penalty rather than crash.
    """
    t = str(getattr(cfd_cfg, "post_folder", "100"))
    try:
        Q = abs(_scalar(case_dir, "Q_ru_in", t))
        ptot_in = _scalar(case_dir, "ptot_ru_in", t)
        ptot_out = _scalar(case_dir, "ptot_ru_out", t)
        moment_z = _moment_z(case_dir, t)
        vcav = abs(_scalar(case_dir, "V_CAV", t))

        # Reject a run that stopped before endTime. The reference raises
        # "Max number of iterations not reached" here; without it a diverged or
        # truncated solve enters the objective looking perfectly valid, and the
        # DE happily optimises towards whatever the broken case reported.
        end_time = getattr(cfd_cfg, "end_time", None)
        if end_time is not None:
            last_it = _last_time(case_dir, "ptot_ru_in", t)
            if abs(last_it - float(end_time)) > 1e-6:
                return {"ok": False,
                        "error": f"Max number of iterations not reached "
                                 f"(last={last_it:g}, expected={float(end_time):g})",
                        "eta": 0.0, "vcav": 0.0, "dH": 0.0, "P": 0.0, "Q": 0.0}

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
