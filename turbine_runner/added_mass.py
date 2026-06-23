"""Wet (added-mass) eigenfrequencies — DEFERRED extension, interface + level-1 model.

Decision (b): dry modes now, wet modes later, with parallel dry-vs-wet comparison.

Physics: a static fluid has no resonance of its own. Its only modal effect is
inertial *added mass* on the wetted surface, which lowers the wet eigenfrequencies
relative to the dry (in-vacuo) ones. For a single mode the shift is

    f_wet = f_dry / sqrt(1 + m_a / m_struct)

where m_a is the modal added mass. The proper level-1 (Rayleigh) computation per
dry mode shape phi solves a Laplace problem for the velocity potential psi on the
fluid domain with Neumann data phi.n on the wetted surface, then

    m_a = rho_fluid * integral_Gamma( psi * (phi.n) ) dGamma

That Laplace solve needs the fluid mesh + wetted-surface tagging and is done with
dolfinx (see TODO below). This module currently provides:
  * the interface the solver/optimizer call (`wet_from_ratios`, `compare`),
  * a configurable placeholder ratio so the parallel dry/wet *plumbing* is testable
    end to end before the Laplace solve lands.

numpy-only so it imports on the host without dolfinx.
"""

import numpy as np


def wet_from_ratios(dry_freqs, added_mass_ratios) -> np.ndarray:
    """Wet frequencies from dry frequencies and per-mode added-mass ratios m_a/m_s.

    f_wet = f_dry / sqrt(1 + ratio). ratio >= 0 -> wet <= dry (always).
    """
    f = np.asarray(dry_freqs, dtype=float)
    r = np.asarray(added_mass_ratios, dtype=float)
    if r.shape != f.shape:
        raise ValueError(f"ratio shape {r.shape} != freq shape {f.shape}")
    if np.any(r < 0):
        raise ValueError("added-mass ratios must be >= 0 (wet cannot exceed dry)")
    return f / np.sqrt(1.0 + r)


def placeholder_ratios(dry_freqs, wet_cfg) -> np.ndarray:
    """Stand-in added-mass ratios until the Laplace solve lands.

    Uses a single constant ratio derived from the fluid/structure density contrast
    as a crude, clearly-flagged placeholder. Replace with `rayleigh_ratios`.
    """
    f = np.asarray(dry_freqs, dtype=float)
    # crude constant: heavier fluid -> larger added mass. NOT physical per-mode.
    ratio = 0.3 * (wet_cfg.rho_fluid / 7850.0) * 10.0
    return np.full(f.shape, ratio)


def rayleigh_ratios(dry_freqs, mode_shapes, domain, wet_cfg):  # pragma: no cover
    """Per-mode added-mass ratio via the level-1 Laplace solve. NOT YET IMPLEMENTED.

    TODO (cluster / dolfinx): for each dry mode shape phi_i
      1. build/identify the fluid domain mesh and the wetted surface Gamma,
      2. solve  div(grad psi)=0 in fluid,  dpsi/dn = phi_i . n  on Gamma,  psi=0 far,
      3. m_a,i = rho_fluid * assemble( psi_i * (phi_i . n) ) over Gamma,
      4. ratio_i = m_a,i / m_struct,i  (m_struct,i = modal mass from the dry solve).
    """
    raise NotImplementedError(
        "rayleigh_ratios requires the fluid-domain Laplace solve (dolfinx). "
        "Use placeholder_ratios for plumbing tests; see HANDOFF.md."
    )


def compare(dry_freqs, wet_cfg, mode_shapes=None, domain=None) -> dict:
    """Return dry and wet frequencies side by side (decision (b) comparison).

    Falls back to placeholder ratios until `rayleigh_ratios` is implemented.
    """
    dry = np.asarray(dry_freqs, dtype=float)
    try:
        ratios = rayleigh_ratios(dry, mode_shapes, domain, wet_cfg)
        method = wet_cfg.method
    except NotImplementedError:
        ratios = placeholder_ratios(dry, wet_cfg)
        method = "placeholder"
    wet = wet_from_ratios(dry, ratios)
    return {
        "method": method,
        "dry_hz": [float(x) for x in dry],
        "wet_hz": [float(x) for x in wet],
        "added_mass_ratio": [float(x) for x in np.atleast_1d(ratios)],
        "shift_pct": [float(100.0 * (w - d) / d) if d else 0.0
                      for d, w in zip(dry, wet)],
    }
