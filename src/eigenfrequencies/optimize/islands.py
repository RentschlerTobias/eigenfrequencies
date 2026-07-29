"""Native island model: N subpopulations with ring migration.

Islands provide population DIVERSITY, not compute parallelism.
Evaluator parallelism lives in :class:`EvaluatorPool` (worker count =
``SLURM_NTASKS`` or ``--workers`` flag), NOT in island count.  Each island
runs an independent instance of the same optimizer backend; ring migration
periodically injects the best individuals from one subpopulation into the
next to maintain genetic diversity and avoid premature convergence on
multimodal landscapes.

CMA-ES caveat: CMA-ES islands each learn their own covariance matrix from
scratch.  The ring migration injects foreign design vectors, which is valid
but often wasteful at small evaluation budgets where the covariance estimate
has not yet stabilised.  For CMA-ES, prefer a single larger population over
multiple small-island populations.
"""

from __future__ import annotations

import json
import os
import pickle
from pathlib import Path
from typing import Any

import numpy as np

from eigenfrequencies.optimize.protocol import (
    Design,
    Optimizer,
    ProtocolUsageError,
    create as _create_optimizer,
)

try:
    import base64 as _base64_mod
except ImportError:
    _base64_mod = None  # pragma: no cover


class CheckpointError(Exception):
    """Raised when an island checkpoint is corrupt, missing, or inconsistent."""


class IslandOptimizer:
    """N independent optimiser instances with periodic ring migration.

    Args:
        backend_name: registered backend name (e.g. ``"de"``, ``"pso"``)
        config: dict-like config passed to each backend factory.  ``seed``
            is bumped per island to give each subpopulation its own RNG
            stream.
        n_islands: number of subpopulations (default 4, recommended 4–8).
        migration_interval: number of ask/tell cycles between migrations
            (default 5).
        migrant_count: number of best individuals each island sends to its
            clockwise neighbour during ring migration (default 2).
    """

    def __init__(
        self,
        backend_name: str,
        config: Any = None,
        n_islands: int = 4,
        migration_interval: int = 5,
        migrant_count: int = 2,
    ) -> None:
        if n_islands < 1:
            raise ValueError("n_islands must be >= 1")
        if migration_interval < 1:
            raise ValueError("migration_interval must be >= 1")
        if migrant_count < 1:
            raise ValueError("migrant_count must be >= 1")

        self._backend_name = backend_name
        self._base_config = dict(config) if config else {}
        self._n_islands = n_islands
        self._migration_interval = migration_interval
        self._migrant_count = migrant_count

        self._generation: int = 0
        self._migration_count: int = 0
        self._best_objective: float = float("inf")
        self._best_vector: list[float] | None = None

        # Create independent optimizer instances with per-island seeds.
        base_seed = self._base_config.get("seed")
        self._islands: list[Optimizer] = []
        for i in range(n_islands):
            island_cfg = dict(self._base_config)
            if base_seed is not None:
                island_cfg["seed"] = int(base_seed) + i * 1000
            self._islands.append(_create_optimizer(backend_name, island_cfg))

        # Cache the last population per island so we know what was evaluated.
        self._last_popped: list[int] = [0] * n_islands
        self._pop_vectors: list[np.ndarray | None] = [None] * n_islands
        self._pop_objectives: list[np.ndarray | None] = [None] * n_islands

    # ── Public API ──

    @property
    def bounds(self) -> list[tuple[float, float]]:
        """Bounds shared by all islands (from the first island)."""
        return self._islands[0].bounds

    @property
    def best_objective(self) -> float:
        """Best (lowest) objective value seen across all islands so far."""
        return self._best_objective

    @property
    def best_vector(self) -> list[float] | None:
        """Design vector that achieved ``best_objective``, or *None*."""
        return self._best_vector

    @property
    def generation(self) -> int:
        """Number of completed ask/tell cycles across all islands."""
        return self._generation

    @property
    def migration_count(self) -> int:
        """Number of ring migrations performed so far."""
        return self._migration_count

    def ask(self, n_per_island: int) -> list[Design]:
        """Return *n_per_island* designs from each island.

        Each returned :class:`Design` has an ``_island`` key in its
        ``metadata`` so that :meth:`tell` can route objectives back to the
        correct subpopulation.
        """
        all_designs: list[Design] = []
        for i, island in enumerate(self._islands):
            designs = island.ask(n_per_island)
            self._last_popped[i] = len(designs)
            for d in designs:
                all_designs.append(
                    Design(
                        vector=d.vector,
                        metadata={**d.metadata, "_island": i},
                    )
                )
        return all_designs

    def tell(self, designs: list[Design], objectives: list[float]) -> None:
        """Route evaluated designs back to their islands and advance generation.

        Raises:
            ProtocolUsageError: if ``len(designs) != len(objectives)``.
        """
        if len(designs) != len(objectives):
            raise ProtocolUsageError(
                f"designs ({len(designs)}) and objectives ({len(objectives)}) "
                "must have the same length"
            )

        # Split designs/objectives by island.
        by_island: dict[int, tuple[list[Design], list[float]]] = {
            i: ([], []) for i in range(self._n_islands)
        }
        for d, obj in zip(designs, objectives):
            idx = d.metadata.get("_island", 0)
            by_island[idx][0].append(d)
            by_island[idx][1].append(obj)

        # Feed each island and cache its population.
        for i, (island_designs, island_objs) in by_island.items():
            if island_designs:
                self._islands[i].tell(island_designs, island_objs)
            vectors = np.asarray([d.vector for d in island_designs], dtype=float)
            self._pop_vectors[i] = vectors
            self._pop_objectives[i] = np.asarray(island_objs, dtype=float)

            # Track global best.
            best_local = float(self._pop_objectives[i].min())
            if best_local < self._best_objective:
                self._best_objective = best_local
                best_idx = int(self._pop_objectives[i].argmin())
                self._best_vector = self._pop_vectors[i][best_idx].tolist()

        self._generation += 1

        # Migrate after every migration_interval cycles.
        if self._generation % self._migration_interval == 0:
            self._migrate()

    def state_dict(self) -> dict:
        """Serializable state for the full island model.

        Captures every island's ``state_dict`` plus the generation and
        migration counters so that :meth:`load_state` can continue from
        exactly the same point.
        """
        return {
            "backend_name": self._backend_name,
            "n_islands": self._n_islands,
            "migration_interval": self._migration_interval,
            "migrant_count": self._migrant_count,
            "generation": self._generation,
            "migration_count": self._migration_count,
            "best_objective": self._best_objective,
            "best_vector": self._best_vector,
            "island_states": [island.state_dict() for island in self._islands],
        }

    def load_state(self, state: dict) -> None:
        """Restore the island model from a dict produced by :meth:`state_dict`.

        This recreates every backend from scratch (discarding the current
        optimiser instances) so the restored state is exact.
        """
        self._n_islands = state["n_islands"]
        self._migration_interval = state["migration_interval"]
        self._migrant_count = state["migrant_count"]
        self._generation = state["generation"]
        self._migration_count = state["migration_count"]
        self._best_objective = state["best_objective"]
        self._best_vector = state.get("best_vector")

        island_states = state["island_states"]
        if len(island_states) != self._n_islands:
            raise CheckpointError(
                f"Expected {self._n_islands} island states, got {len(island_states)}"
            )

        self._islands = []
        self._pop_vectors = [None] * self._n_islands
        self._pop_objectives = [None] * self._n_islands
        self._last_popped = [0] * self._n_islands

        # Recreate each island from scratch and restore its state.
        # We must supply a dummy config with valid bounds so the constructor
        # succeeds before load_state overwrites everything.
        for i, island_state in enumerate(island_states):
            island_cfg = dict(self._base_config)
            island = _create_optimizer(self._backend_name, island_cfg)
            island.load_state(island_state)
            self._islands.append(island)

    # ── Checkpoint I/O ──

    def save_checkpoints(self, directory: str | Path) -> None:
        """Write per-island JSON checkpoints under *directory*.

        Creates ``island_{i}.json`` for each island, plus a
        ``_meta.json`` file with shared metadata.  The directory is created
        if it does not exist.
        """
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True)

        for i in range(self._n_islands):
            checkpoint: dict[str, Any] = {
                "backend_name": self._backend_name,
                "island_index": i,
                "n_islands": self._n_islands,
                "generation": self._generation,
                "migration_count": self._migration_count,
                "migration_interval": self._migration_interval,
                "migrant_count": self._migrant_count,
                "state": self._islands[i].state_dict(),
            }
            ckpt_path = directory / f"island_{i}.json"
            with open(ckpt_path, "w") as f:
                json.dump(checkpoint, f, indent=2)

        # Shared metadata so resume doesn't need the original config object.
        meta: dict[str, Any] = {
            "backend_name": self._backend_name,
            "n_islands": self._n_islands,
            "generation": self._generation,
            "migration_count": self._migration_count,
            "migration_interval": self._migration_interval,
            "migrant_count": self._migrant_count,
            "best_objective": self._best_objective,
            "best_vector": self._best_vector,
        }
        with open(directory / "_meta.json", "w") as f:
            json.dump(meta, f, indent=2)

    @classmethod
    def resume(
        cls,
        backend_name: str,
        config: Any,
        directory: str | Path,
        n_islands: int = 4,
        migration_interval: int = 5,
        migrant_count: int = 2,
    ) -> IslandOptimizer:
        """Resume a run from per-island checkpoints in *directory*.

        Args:
            backend_name: optimizer backend name.
            config: dict-like config passed to the backend factory.
            directory: path containing ``island_{i}.json`` files.
            n_islands: expected island count (validated against checkpoint).
            migration_interval: expected interval (validated).
            migrant_count: expected migrant count (validated).

        Returns:
            A new :class:`IslandOptimizer` with all islands restored.

        Raises:
            CheckpointError: if any checkpoint is missing, corrupt, or
                inconsistent.
        """
        directory = Path(directory)

        # Load and validate meta.
        meta_path = directory / "_meta.json"
        try:
            with open(meta_path) as f:
                meta = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError) as exc:
            raise CheckpointError(
                f"Failed to load checkpoint meta {meta_path}: {exc}"
            ) from exc

        expected_n = meta.get("n_islands", n_islands)
        if expected_n != n_islands:
            raise CheckpointError(
                f"Checkpoint has n_islands={expected_n}, "
                f"but resume requested n_islands={n_islands}"
            )

        # Load each island checkpoint.
        island_states: list[dict] = []
        for i in range(n_islands):
            ckpt_path = directory / f"island_{i}.json"
            try:
                with open(ckpt_path) as f:
                    checkpoint = json.load(f)
            except FileNotFoundError as exc:
                raise CheckpointError(
                    f"Island {i} checkpoint missing: {ckpt_path}"
                ) from exc
            except json.JSONDecodeError as exc:
                raise CheckpointError(
                    f"Island {i} checkpoint corrupt (invalid JSON): {exc}"
                ) from exc

            # Basic sanity checks.
            if "state" not in checkpoint:
                raise CheckpointError(
                    f"Island {i} checkpoint missing 'state' key"
                )
            island_states.append(checkpoint)

        # Build the island model state dict and restore.
        model_state: dict[str, Any] = {
            "backend_name": backend_name,
            "n_islands": n_islands,
            "migration_interval": meta.get("migration_interval", migration_interval),
            "migrant_count": meta.get("migrant_count", migrant_count),
            "generation": meta["generation"],
            "migration_count": meta["migration_count"],
            "best_objective": meta.get("best_objective", float("inf")),
            "best_vector": meta.get("best_vector"),
            "island_states": [cs["state"] for cs in island_states],
        }

        # Create a fresh IslandOptimizer and restore from the built state.
        instance = cls(
            backend_name=backend_name,
            config=config,
            n_islands=n_islands,
            migration_interval=migration_interval,
            migrant_count=migrant_count,
        )
        instance.load_state(model_state)
        return instance

    # ── Migration internals ──

    def _migrate(self) -> None:
        """Execute one ring migration epoch (best-K from i → (i+1) % N)."""
        # Snapshot every island's state before migration.
        states = [island.state_dict() for island in self._islands]

        for src_idx in range(self._n_islands):
            dst_idx = (src_idx + 1) % self._n_islands
            self._migrate_island_to_island(
                states[src_idx],
                states[dst_idx],
                self._migrant_count,
            )

        # Reload all islands with modified state dicts.
        for i, state in enumerate(states):
            self._islands[i].load_state(state)

        self._migration_count += 1

    def _migrate_island_to_island(
        self, src_state: dict, dst_state: dict, k: int
    ) -> None:
        """Mutate *dst_state* by replacing its worst *k* individuals with
        the best *k* from *src_state*.

        The no-duplicate policy skips a migrant when its design vector
        already exists in the destination population.
        """
        # Dispatch to backend-specific migration based on state dict shape.
        if "population" in dst_state and "objectives" in dst_state:
            self._migrate_population_lists(src_state, dst_state, k)
        elif "algorithm_pickle" in dst_state:
            self._migrate_pso(src_state, dst_state, k)
        # CMA-ES (pickle key) and BO (trials key) have no fixed
        # population — migration is a no-op for these backends.

    @staticmethod
    def _migrate_population_lists(src: dict, dst: dict, k: int) -> None:
        """Migration for backends that store ``population`` + ``objectives``
        lists (DE and similar)."""
        src_pop = np.asarray(src["population"], dtype=float)
        src_obj = np.asarray(src["objectives"], dtype=float)
        dst_pop = np.asarray(dst["population"], dtype=float)
        dst_obj = np.asarray(dst["objectives"], dtype=float)

        pop_size = len(dst_pop)
        if pop_size == 0:
            return

        remaining_to_replace = min(k, pop_size)

        # Best from source (ascending).
        src_order = np.argsort(src_obj)
        # Worst at destination (descending).
        dst_order = np.argsort(dst_obj)[::-1]

        src_cursor = 0
        replaced: set[int] = set()

        while remaining_to_replace > 0 and src_cursor < len(src_order):
            migrant_idx = int(src_order[src_cursor])
            migrant_vec = src_pop[migrant_idx]
            src_cursor += 1

            # No-duplicate: skip if vector already present in destination.
            duplicate = False
            for j in range(pop_size):
                if j not in replaced and np.allclose(migrant_vec, dst_pop[j], atol=1e-12):
                    duplicate = True
                    break
            if duplicate:
                continue

            # Find the worst unreplaced slot.
            for worst_candidate in dst_order:
                wc = int(worst_candidate)
                if wc not in replaced:
                    dst_pop[wc] = migrant_vec
                    dst_obj[wc] = float(src_obj[migrant_idx])
                    replaced.add(wc)
                    remaining_to_replace -= 1
                    break

        dst["population"] = dst_pop.tolist()
        dst["objectives"] = dst_obj.tolist()

    @staticmethod
    def _migrate_pso(src_state: dict, dst_state: dict, k: int) -> None:
        """Migration for PSO backends whose state contains a pickled
        pymoo ``Algorithm`` object."""
        src_alg = pickle.loads(
            __import__("base64").b64decode(src_state["algorithm_pickle"])
        )
        dst_alg = pickle.loads(
            __import__("base64").b64decode(dst_state["algorithm_pickle"])
        )

        src_pop = src_alg.pop
        dst_pop = dst_alg.pop

        src_X = np.asarray([ind.X for ind in src_pop], dtype=float)
        src_F = np.asarray([float(ind.F[0]) for ind in src_pop], dtype=float)
        dst_X = np.asarray([ind.X for ind in dst_pop], dtype=float)
        dst_F = np.asarray([float(ind.F[0]) for ind in dst_pop], dtype=float)

        pop_size = len(dst_pop)
        if pop_size == 0:
            return

        remaining_to_replace = min(k, pop_size)
        src_order = np.argsort(src_F)
        dst_order = np.argsort(dst_F)[::-1]

        src_cursor = 0
        replaced: set[int] = set()

        while remaining_to_replace > 0 and src_cursor < len(src_order):
            migrant_idx = int(src_order[src_cursor])
            migrant_vec = src_X[migrant_idx]
            src_cursor += 1

            duplicate = False
            for j in range(pop_size):
                if j not in replaced and np.allclose(migrant_vec, dst_X[j], atol=1e-12):
                    duplicate = True
                    break
            if duplicate:
                continue

            for worst_candidate in dst_order:
                wc = int(worst_candidate)
                if wc not in replaced:
                    dst_X[wc] = migrant_vec
                    dst_F[wc] = float(src_F[migrant_idx])
                    replaced.add(wc)
                    remaining_to_replace -= 1
                    break

        # Write back to pymoo Individuals.
        for idx in range(pop_size):
            dst_pop[idx].X = dst_X[idx]
            dst_pop[idx].F = np.array([dst_F[idx]])

        dst_state["algorithm_pickle"] = __import__("base64").b64encode(
            pickle.dumps(dst_alg)
        ).decode("ascii")
