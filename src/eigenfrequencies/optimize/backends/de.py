"""Custom Differential Evolution (DE) backend behind the Optimizer protocol.

Ports the core algorithm from ``turbine_runner/optimize_de.py``:

* Population-based differential mutation + binomial crossover
* Greedy selection (trial replaces target if better)
* Seeded ``numpy.random.default_rng`` for deterministic runs
* Environment overrides: ``DE_POP_SIZE``, ``DE_F``, ``DE_CR``, ``DE_MAX_GEN``

The remote-evaluation, checkpointing, and progress-bar code from the legacy
file is **not** ported — the protocol keeps the optimizer objective-agnostic.
"""

from __future__ import annotations

import os
from typing import Any

import numpy as np

from eigenfrequencies.optimize.protocol import Design, Optimizer, ProtocolUsageError


class DEOptimizer(Optimizer):
    """Differential Evolution optimizer implementing the ask/tell protocol.

    Args:
        config: dict-like object with optional keys:
            - ``bounds``: list of (min, max) tuples (required if not in config)
            - ``pop_size``: population size (default 20, env override DE_POP_SIZE)
            - ``F``: differential weight (default 0.8, env override DE_F)
            - ``CR``: crossover probability (default 0.9, env override DE_CR)
            - ``max_generations``: max generations (default 30, env override DE_MAX_GEN)
            - ``seed``: int seed for the RNG (default None)
            - ``x0``: optional initial design vector; if provided, the initial
              population is sampled normally around *x0* (legacy behaviour),
              otherwise uniform random inside *bounds*.
            - ``init_spread``: standard deviation fraction for x0-based init
              (default 0.05, env override DE_INIT_SPREAD)
    """

    def __init__(self, config: Any = None) -> None:
        cfg = config or {}
        self._bounds: list[tuple[float, float]] = list(cfg.get("bounds", []))
        if not self._bounds:
            raise ValueError("DEOptimizer requires 'bounds' in config")

        self._dim = len(self._bounds)
        self._low = np.array([b[0] for b in self._bounds], dtype=float)
        self._high = np.array([b[1] for b in self._bounds], dtype=float)
        self._span = self._high - self._low

        # Env overrides take precedence over config dict, which takes precedence
        # over the hard-coded defaults that match the legacy file.
        self._pop_size = int(os.environ.get("DE_POP_SIZE", cfg.get("pop_size", 20)))
        self._F = float(os.environ.get("DE_F", cfg.get("F", 0.8)))
        self._CR = float(os.environ.get("DE_CR", cfg.get("CR", 0.9)))
        self._max_gen = int(os.environ.get("DE_MAX_GEN", cfg.get("max_generations", 30)))
        self._init_spread = float(
            os.environ.get("DE_INIT_SPREAD", cfg.get("init_spread", 0.05))
        )

        seed = cfg.get("seed")
        self._rng = np.random.default_rng(seed)

        self._x0 = cfg.get("x0")
        if self._x0 is not None:
            self._x0 = np.asarray(self._x0, dtype=float)

        # Internal state — populated on first tell()
        self._population: np.ndarray | None = None
        self._objectives: np.ndarray | None = None
        self._generation = 0
        self._best_vec: np.ndarray | None = None
        self._best_obj = float("inf")

    # ── Protocol ──

    @property
    def bounds(self) -> list[tuple[float, float]]:
        return list(self._bounds)

    def ask(self, n: int) -> list[Design]:
        """Return *n* design vectors.

        On the very first call the population is initialised (uniform random
        or around *x0* if provided).  On subsequent calls trial vectors are
        generated via differential mutation + crossover.
        """
        if self._population is None:
            self._population = self._init_population(n)
            return [Design(vector=self._population[i].tolist()) for i in range(n)]

        trials = self._make_trials(n)
        return [Design(vector=trials[i].tolist()) for i in range(n)]

    def tell(self, designs: list[Design], objectives: list[float]) -> None:
        if len(designs) != len(objectives):
            raise ProtocolUsageError(
                f"designs ({len(designs)}) and objectives ({len(objectives)}) "
                "must have the same length"
            )

        trials = np.asarray([d.vector for d in designs], dtype=float)
        trial_obj = np.asarray(objectives, dtype=float)

        if self._objectives is None:
            # First tell — store initial population objectives
            self._objectives = trial_obj.copy()
            best_idx = int(self._objectives.argmin())
            self._best_vec = self._population[best_idx].copy()
            self._best_obj = float(self._objectives[best_idx])
            return

        # Greedy selection: trial replaces target if better
        pop_size = len(self._population)
        for i in range(len(designs)):
            target_idx = i % pop_size
            if trial_obj[i] < self._objectives[target_idx]:
                self._population[target_idx] = trials[i]
                self._objectives[target_idx] = trial_obj[i]

        # Update global best
        best_idx = int(self._objectives.argmin())
        if float(self._objectives[best_idx]) < self._best_obj:
            self._best_vec = self._population[best_idx].copy()
            self._best_obj = float(self._objectives[best_idx])

        self._generation += 1

    def state_dict(self) -> dict:
        """Serializable state for checkpointing."""
        state: dict[str, Any] = {
            "bounds": self._bounds,
            "dim": self._dim,
            "pop_size": self._pop_size,
            "F": self._F,
            "CR": self._CR,
            "max_gen": self._max_gen,
            "generation": self._generation,
            "best_obj": self._best_obj,
            "rng_state": self._rng.bit_generator.state,
        }
        if self._population is not None:
            state["population"] = self._population.tolist()
        if self._objectives is not None:
            state["objectives"] = self._objectives.tolist()
        if self._best_vec is not None:
            state["best_vec"] = self._best_vec.tolist()
        if self._x0 is not None:
            state["x0"] = self._x0.tolist()
        return state

    def load_state(self, state: dict) -> None:
        """Restore from a dict produced by ``state_dict``."""
        self._bounds = [tuple(b) for b in state["bounds"]]
        self._dim = state["dim"]
        self._pop_size = state["pop_size"]
        self._F = state["F"]
        self._CR = state["CR"]
        self._max_gen = state["max_gen"]
        self._generation = state["generation"]
        self._best_obj = state["best_obj"]

        self._low = np.array([b[0] for b in self._bounds], dtype=float)
        self._high = np.array([b[1] for b in self._bounds], dtype=float)
        self._span = self._high - self._low

        if "population" in state:
            self._population = np.asarray(state["population"], dtype=float)
        else:
            self._population = None

        if "objectives" in state:
            self._objectives = np.asarray(state["objectives"], dtype=float)
        else:
            self._objectives = None

        if "best_vec" in state:
            self._best_vec = np.asarray(state["best_vec"], dtype=float)
        else:
            self._best_vec = None

        if "x0" in state:
            self._x0 = np.asarray(state["x0"], dtype=float)
        else:
            self._x0 = None

        self._rng.bit_generator.state = state["rng_state"]

    # ── Internals ──

    def _init_population(self, n: int) -> np.ndarray:
        """Create an initial population of *n* individuals."""
        if self._x0 is not None:
            # Legacy behaviour: sample around the template vector
            pop = self._x0 + self._rng.normal(
                0.0, self._init_spread, size=(n, self._dim)
            ) * self._span
            pop = np.clip(pop, self._low, self._high)
            pop[0] = self._x0
        else:
            pop = self._rng.uniform(self._low, self._high, size=(n, self._dim))
        return pop.astype(float)

    def _make_trials(self, n: int) -> np.ndarray:
        """Generate *n* trial vectors via DE/rand/1/bin."""
        pop_size = len(self._population)
        trials = np.zeros((n, self._dim), dtype=float)
        for i in range(n):
            target_idx = i % pop_size
            a, b, c = self._rng.choice(pop_size, size=3, replace=False)
            mutant = self._population[a] + self._F * (
                self._population[b] - self._population[c]
            )
            mutant = np.clip(mutant, self._low, self._high)

            cross = self._rng.random(self._dim) < self._CR
            if not cross.any():
                cross[self._rng.integers(self._dim)] = True
            trial = np.where(cross, mutant, self._population[target_idx])
            trials[i] = trial
        return trials
