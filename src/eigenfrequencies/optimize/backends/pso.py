"""PSO backend wrapping ``pymoo.algorithms.soo.nonconvex.pso.PSO`` behind the
Optimizer protocol.

Uses pymoo's native ask/tell interface:

* ``ask()`` returns the offspring population (new particle positions).
* ``tell(infills=pop)`` advances the swarm after objectives are attached.

The wrapper buffers partial evaluations: if the caller requests fewer designs
than ``pop_size`` in one ``ask()``, the remaining individuals are returned on
the next ``ask()`` until the full population has been evaluated and the
algorithm can advance.

Lazy import: the module is importable without *pymoo* installed; instantiating
``PSOOptimizer`` raises a clear runtime error when the package is missing.
"""

from __future__ import annotations

import base64
import pickle
from typing import Any

import numpy as np

from eigenfrequencies.optimize.protocol import Design, Optimizer, ProtocolUsageError


class PSOOptimizer(Optimizer):
    """Particle Swarm Optimizer implementing the ask/tell protocol.

    Args:
        config: dict-like object with optional keys:
            - ``bounds``: list of (min, max) tuples (required)
            - ``pop_size``: swarm size (default 25, pymoo default)
            - ``seed``: int seed for the RNG (default None)
    """

    def __init__(self, config: Any = None) -> None:
        try:
            from pymoo.algorithms.soo.nonconvex.pso import PSO
            from pymoo.core.problem import Problem
        except Exception:
            raise RuntimeError("unavailable: pymoo not installed") from None

        self._PSO = PSO
        self._Problem = Problem

        cfg = config or {}
        self._bounds: list[tuple[float, float]] = list(cfg.get("bounds", []))
        if not self._bounds:
            raise ValueError("PSOOptimizer requires 'bounds' in config")

        self._dim = len(self._bounds)
        self._pop_size = int(cfg.get("pop_size", 25))
        self._seed = cfg.get("seed")

        xl = np.array([b[0] for b in self._bounds], dtype=float)
        xu = np.array([b[1] for b in self._bounds], dtype=float)
        self._problem = self._Problem(n_var=self._dim, n_obj=1, xl=xl, xu=xu)

        self._algorithm = self._PSO(pop_size=self._pop_size)
        self._algorithm.setup(
            self._problem,
            termination=("n_gen", 100_000),
            seed=self._seed,
            verbose=False,
        )

        # Partial-evaluation bookkeeping
        self._pending_pop: Any | None = None
        self._pending_evaluated: set[int] = set()
        self._generation = 0

    # ── Protocol ──

    @property
    def bounds(self) -> list[tuple[float, float]]:
        return list(self._bounds)

    def ask(self, n: int) -> list[Design]:
        """Return *n* design vectors from the current swarm."""
        # If there are still unevaluated individuals from a previous ask,
        # return those first.
        if self._pending_pop is not None and len(self._pending_evaluated) < len(
            self._pending_pop
        ):
            remaining = [
                i
                for i in range(len(self._pending_pop))
                if i not in self._pending_evaluated
            ]
            count = min(n, len(remaining))
            indices = remaining[:count]
            return [
                Design(
                    vector=self._pending_pop[i].X.tolist(),
                    metadata={"_pso_idx": i},
                )
                for i in indices
            ]

        # Fresh generation: ask pymoo for the full offspring population.
        self._pending_pop = self._algorithm.ask()
        self._pending_evaluated = set()

        count = min(n, len(self._pending_pop))
        return [
            Design(
                vector=self._pending_pop[i].X.tolist(),
                metadata={"_pso_idx": i},
            )
            for i in range(count)
        ]

    def tell(self, designs: list[Design], objectives: list[float]) -> None:
        if len(designs) != len(objectives):
            raise ProtocolUsageError(
                f"designs ({len(designs)}) and objectives ({len(objectives)}) "
                "must have the same length"
            )

        if self._pending_pop is None:
            raise ProtocolUsageError("tell() called without a preceding ask()")

        for d, obj in zip(designs, objectives):
            idx = d.metadata.get("_pso_idx")
            if idx is None:
                raise ProtocolUsageError("Design missing _pso_idx metadata")
            if not (0 <= idx < len(self._pending_pop)):
                raise ProtocolUsageError(f"Invalid _pso_idx: {idx}")
            self._pending_pop[idx].F = np.array([obj])
            self._pending_evaluated.add(idx)

        # Advance the algorithm only when every individual has been evaluated.
        if len(self._pending_evaluated) == len(self._pending_pop):
            self._algorithm.tell(infills=self._pending_pop)
            self._pending_pop = None
            self._pending_evaluated = set()
            self._generation += 1

    def state_dict(self) -> dict:
        """Serializable state for checkpointing."""
        state: dict[str, Any] = {
            "bounds": self._bounds,
            "dim": self._dim,
            "pop_size": self._pop_size,
            "seed": self._seed,
            "generation": self._generation,
        }

        if self._algorithm is not None:
            state["algorithm_pickle"] = base64.b64encode(
                pickle.dumps(self._algorithm)
            ).decode("ascii")

        if self._pending_pop is not None:
            state["pending_pop"] = [
                {
                    "X": ind.X.tolist(),
                    "F": ind.F.tolist()
                    if ind.F is not None and len(ind.F) > 0
                    else None,
                }
                for ind in self._pending_pop
            ]
            state["pending_evaluated"] = sorted(self._pending_evaluated)

        return state

    def load_state(self, state: dict) -> None:
        """Restore optimizer state from a dict produced by ``state_dict``."""
        self._bounds = [tuple(b) for b in state["bounds"]]
        self._dim = state["dim"]
        self._pop_size = state["pop_size"]
        self._seed = state.get("seed")
        self._generation = state.get("generation", 0)

        if "algorithm_pickle" in state:
            self._algorithm = pickle.loads(
                base64.b64decode(state["algorithm_pickle"].encode("ascii"))
            )

        self._pending_pop = None
        self._pending_evaluated = set()

        if "pending_pop" in state:
            from pymoo.core.individual import Individual
            from pymoo.core.population import Population

            individuals = []
            for item in state["pending_pop"]:
                ind = Individual(X=np.array(item["X"], dtype=float))
                if item["F"] is not None:
                    ind.F = np.array(item["F"], dtype=float)
                individuals.append(ind)

            self._pending_pop = Population.new(
                X=np.array([ind.X for ind in individuals], dtype=float)
            )
            # Re-attach F values
            for i, ind in enumerate(self._pending_pop):
                if individuals[i].F is not None and len(individuals[i].F) > 0:
                    ind.F = individuals[i].F

            self._pending_evaluated = set(state.get("pending_evaluated", []))
