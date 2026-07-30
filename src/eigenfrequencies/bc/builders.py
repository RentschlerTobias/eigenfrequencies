"""Boundary-condition builders for runner modal analysis.

Provides factory functions that return configured ``BCConfig`` instances for
common clamp/free-free/foil-clamp scenarios.  The hub-clamp predicate logic is
extracted from ``turbine_runner/solver.py`` and made reusable.
"""

from typing import Callable, Optional, Tuple

import numpy as np

from eigenfrequencies.config import BCConfig


_AXIS_INDEX = {"x": 0, "y": 1, "z": 2}


def clamp(
    axis: str = "z",
    hub_center: Tuple[float, float] = (0.0, 0.0),
    hub_radius: float = 0.15,
    axial_min: Optional[float] = None,
    axial_max: Optional[float] = None,
    plane_value: float = 0.0,
    plane_tol: float = 1e-6,
) -> BCConfig:
    """Return a ``BCConfig`` for a radius-band clamp at the hub.

    Parameters match ``BCConfig`` fields.  ``mode`` is set to ``"radius_band"``.
    """
    return BCConfig(
        axis=axis,
        hub_center=hub_center,
        hub_radius=hub_radius,
        axial_min=axial_min,
        axial_max=axial_max,
        mode="radius_band",
        plane_value=plane_value,
        plane_tol=plane_tol,
    )


def free_free() -> BCConfig:
    """Return a ``BCConfig`` for free-free vibration (no clamp).

    The 6 rigid-body modes are expected and must be discarded downstream.
    """
    return BCConfig(mode="free")


def foil_clamp(
    axis: str = "z",
    plane_value: float = 0.0,
    plane_tol: float = 1e-6,
) -> BCConfig:
    """Return a ``BCConfig`` for an axial-plane clamp (e.g. foil disc at z=0).

    This is the configuration used by the test-case validation disc.
    """
    return BCConfig(
        axis=axis,
        mode="axial_plane",
        plane_value=plane_value,
        plane_tol=plane_tol,
    )


def hub_clamp(
    axis: str = "z",
    hub_center: Tuple[float, float] = (0.0, 0.0),
    hub_radius: float = 0.15,
    axial_min: Optional[float] = None,
    axial_max: Optional[float] = None,
) -> BCConfig:
    """Return a ``BCConfig`` for the runner hub clamp (alias for ``clamp``).

    This is the default boundary condition for the turbine runner: nodes within
    ``hub_radius`` of the rotation axis, optionally restricted to an axial band.
    """
    return clamp(
        axis=axis,
        hub_center=hub_center,
        hub_radius=hub_radius,
        axial_min=axial_min,
        axial_max=axial_max,
    )


def build_predicate(cfg: BCConfig) -> Optional[Callable]:
    """Build a coordinate predicate function from a ``BCConfig``.

    The predicate accepts a ``(3, n_points)`` array ``x`` and returns a boolean
    mask of length ``n_points``.  Returns ``None`` for free-free mode.

    This is the logic extracted from ``turbine_runner/solver.py``.
    """
    if cfg.mode == "free":
        return None
    if cfg.axis not in _AXIS_INDEX:
        raise ValueError(f"BCConfig.axis must be x/y/z, got {cfg.axis!r}")
    ai = _AXIS_INDEX[cfg.axis]
    p, q = [i for i in range(3) if i != ai]
    c1, c2 = cfg.hub_center

    if cfg.mode == "axial_plane":
        def predicate(x):
            return np.isclose(x[ai], cfg.plane_value, atol=cfg.plane_tol)
        return predicate

    if cfg.mode == "radius_band":
        def predicate(x):
            radius = np.sqrt((x[p] - c1) ** 2 + (x[q] - c2) ** 2)
            sel = radius <= cfg.hub_radius
            if cfg.axial_min is not None:
                sel = sel & (x[ai] >= cfg.axial_min)
            if cfg.axial_max is not None:
                sel = sel & (x[ai] <= cfg.axial_max)
            return sel
        return predicate

    raise ValueError(
        f"BCConfig.mode must be 'radius_band', 'axial_plane', or 'free', got {cfg.mode!r}"
    )
