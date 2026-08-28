"""CMA-ES backend wrapping ``cma.CMAEvolutionStrategy`` (native ask/tell).

* ``x0`` defaults to the centre of the bounds.
* ``sigma0`` defaults to ``0.3 * max(bounds_range)``, overridable via config.
* Seeded via ``np.random.RandomState`` passed as ``randn`` for deterministic runs.
* Lazy import: the module is importable without ``cma`` installed; instantiation
  raises ``ImportError`` when the package is missing.
"""

from __future__ import annotations

import pickle
import warnings
from typing import Any

import numpy as np

from eigenfrequencies.optimize.protocol import Design, Optimizer, ProtocolUsageError


class CMAESOptimizer(Optimizer):
    """CMA-ES optimizer implementing the ask/tell protocol.

    Args:
        config: dict-like object with optional keys:
            - ``bounds``: list of (min, max) tuples (required)
            - ``x0``: initial mean vector (default: centre of bounds)
            - ``sigma0``: initial step-size (default: 0.3 * max(bounds_range))
            - ``seed``: int seed for the RNG (default: None)
            - ``popsize``: population size (default: CMA-ES auto)
    """

    def __init__(self, config: Any = None) -> None:
        try:
            import cma  # noqa: F811
        except ImportError:
            raise ImportError("unavailable: cma not installed") from None

        cfg = config or {}
        self._bounds: list[tuple[float, float]] = list(cfg.get("bounds", []))
        if not self._bounds:
            raise ValueError("CMAESOptimizer requires 'bounds' in config")

        self._dim = len(self._bounds)
        self._low = np.array([b[0] for b in self._bounds], dtype=float)
        self._high = np.array([b[1] for b in self._bounds], dtype=float)
        self._span = self._high - self._low

        # x0 defaults to centre of bounds
        x0 = cfg.get("x0")
        if x0 is not None:
            self._x0 = np.asarray(x0, dtype=float)
        else:
            self._x0 = (self._low + self._high) / 2.0

        # sigma0 defaults to 0.3 * max(bounds_range), configurable
        sigma0 = cfg.get("sigma0")
        if sigma0 is not None:
            self._sigma0 = float(sigma0)
        else:
            self._sigma0 = 0.3 * float(np.max(self._span))

        # Seed handling: use a private RandomState so the global numpy RNG
        # is untouched and runs are reproducible.
        seed = cfg.get("seed")
        if seed is not None:
            rng = np.random.RandomState(int(seed))
            randn = rng.randn
        else:
            randn = np.random.randn

        # CMA-ES bounds format: [lower_bounds, upper_bounds]
        cma_bounds = [self._low.tolist(), self._high.tolist()]

        opts: dict[str, Any] = {
            "bounds": cma_bounds,
            "verbose": -1,
            "randn": randn,
        }

        popsize = cfg.get("popsize")
        if popsize is not None:
            opts["popsize"] = int(popsize)

        with warnings.catch_warnings():
            warnings.filterwarnings(
                "ignore",
                message="seed=time will never be used.*",
            )
            self._es = cma.CMAEvolutionStrategy(
                self._x0.tolist(),
                self._sigma0,
                opts,
            )

        self._last_asked: list[np.ndarray] | None = None

    # ── Protocol ──

    @property
    def bounds(self) -> list[tuple[float, float]]:
        return list(self._bounds)

    def ask(self, n: int) -> list[Design]:
        """Return *n* design vectors sampled from the CMA-ES distribution."""
        solutions = self._es.ask(number=n)
        self._last_asked = [np.asarray(s, dtype=float) for s in solutions]
        return [Design(vector=s.tolist()) for s in self._last_asked]

    def tell(self, designs: list[Design], objectives: list[float]) -> None:
        if len(designs) != len(objectives):
            raise ProtocolUsageError(
                f"designs ({len(designs)}) and objectives ({len(objectives)}) "
                "must have the same length"
            )

        solutions = [np.asarray(d.vector, dtype=float) for d in designs]

        # CMA-ES warns when the number of solutions differs from the internal
        # popsize.  The warning is harmless for our ask/tell protocol, so we
        # suppress it.
        with warnings.catch_warnings():
            warnings.filterwarnings(
                "ignore",
                message="The number of solutions passed to `tell` should.*",
            )
            self._es.tell(solutions, objectives)

        self._last_asked = None

    def state_dict(self) -> dict:
        """Serializable state for checkpointing (pickle-backed)."""
        return {
            "bounds": self._bounds,
            "dim": self._dim,
            "x0": self._x0.tolist(),
            "sigma0": self._sigma0,
            "pickle": pickle.dumps(self._es).hex(),
        }

    def load_state(self, state: dict) -> None:
        """Restore optimizer state from a dict produced by ``state_dict``."""
        self._bounds = [tuple(b) for b in state["bounds"]]
        self._dim = state["dim"]
        self._x0 = np.asarray(state["x0"], dtype=float)
        self._sigma0 = state["sigma0"]
        self._low = np.array([b[0] for b in self._bounds], dtype=float)
        self._high = np.array([b[1] for b in self._bounds], dtype=float)
        self._span = self._high - self._low
        self._es = pickle.loads(bytes.fromhex(state["pickle"]))
        self._last_asked = None
