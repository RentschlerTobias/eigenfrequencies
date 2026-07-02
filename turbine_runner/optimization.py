"""Resonance-avoidance penalty for the runner eigenfrequencies.

Multi-harmonic forbidden bands: the blade-passing frequency f_bp = Z·n/60
and its harmonics (1× to max_harmonic) each define a forbidden interval.

Any eigenfrequency inside any interval is penalised by how far it sits
inside that interval; frequencies outside all intervals contribute nothing.
"""

import numpy as np


def _forbidden_intervals(opt_cfg):
    """Return list of (lo, hi) tuples for each harmonic forbidden band."""
    f_bp = opt_cfg.Z_guidevanes * opt_cfg.n_rpm / 60.0
    intervals = []
    for h in range(1, opt_cfg.max_harmonic + 1):
        center = h * f_bp
        margin = max(opt_cfg.margin_hz, center * opt_cfg.margin_fraction)
        lo = center - margin
        hi = center + margin
        intervals.append((lo, hi))
    return intervals


def compute_penalty(frequencies, opt_cfg) -> float:
    """Penalty = sum over modes inside any forbidden interval of k * depth.

    A frequency exactly at an interval edge contributes 0; one at the centre
    contributes the most. Zero penalty means no mode lies in any interval.
    """
    f = np.asarray(frequencies, dtype=float)
    intervals = _forbidden_intervals(opt_cfg)
    total = 0.0
    for lo, hi in intervals:
        mask = (f >= lo) & (f <= hi)
        inside = f[mask]
        if inside.size == 0:
            continue
        depth = np.minimum(inside - lo, hi - inside)
        total += opt_cfg.penalty_k * np.sum(depth)
    return float(total)


def band_report(frequencies, opt_cfg) -> str:
    """Human-readable summary of which modes violate any forbidden interval."""
    f = np.asarray(frequencies, dtype=float)
    intervals = _forbidden_intervals(opt_cfg)
    all_violators = []
    for lo, hi in intervals:
        violators = [(i + 1, v) for i, v in enumerate(f) if lo <= v <= hi]
        for i, v in violators:
            all_violators.append(f"mode {i}={v:.1f}Hz")
    if not all_violators:
        parts = ", ".join(f"[{lo:.1f},{hi:.1f}]" for lo, hi in intervals)
        return f"OK: no mode in forbidden bands: {parts}"
    return f"VIOLATION: {', '.join(all_violators)}"
