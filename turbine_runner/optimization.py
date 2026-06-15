"""Resonance-avoidance penalty for the runner eigenfrequencies.

Pure / dependency-light (numpy only) so it can be imported on the host optimizer
side as well as inside the FEniCSx container. Mirrors the penalty idea of
demo/beam/optimization.py but for a forbidden band: any eigenfrequency inside
[f_min, f_max] (widened by `margin`) is penalized by how far it sits inside the
band; frequencies outside contribute nothing.
"""

import numpy as np


def compute_penalty(frequencies, opt_cfg) -> float:
    """Penalty = sum over modes inside the forbidden band of k * inside-depth.

    A frequency exactly at a band edge contributes 0; one at the band center
    contributes the most. Zero penalty means no mode lies in the band.
    """
    f = np.asarray(frequencies, dtype=float)
    lo = opt_cfg.f_min - opt_cfg.margin
    hi = opt_cfg.f_max + opt_cfg.margin
    inside = f[(f >= lo) & (f <= hi)]
    if inside.size == 0:
        return 0.0
    # Depth inside the band: distance to the nearest edge (0 at edges, max mid).
    depth = np.minimum(inside - lo, hi - inside)
    return float(opt_cfg.penalty_k * np.sum(depth))


def band_report(frequencies, opt_cfg) -> str:
    """Human-readable summary of which modes violate the forbidden band."""
    f = np.asarray(frequencies, dtype=float)
    lo = opt_cfg.f_min - opt_cfg.margin
    hi = opt_cfg.f_max + opt_cfg.margin
    violators = [(i + 1, v) for i, v in enumerate(f) if lo <= v <= hi]
    if not violators:
        return f"OK: no mode in forbidden band [{lo:.1f}, {hi:.1f}] Hz"
    parts = ", ".join(f"mode {i}={v:.1f}Hz" for i, v in violators)
    return f"VIOLATION in [{lo:.1f}, {hi:.1f}] Hz: {parts}"
