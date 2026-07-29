"""Gymnasium environment wrapping the eigenfrequency objective for RL.

Action space is a Box(-1, 1, shape=(dim,)) mapped linearly to the design
bounds. Observation is the normalized design vector (0..1 per component)
concatenated with the last objective value. Reward = -objective(design)
so the agent learns to minimise the objective by maximising reward.
"""

from __future__ import annotations

from typing import Callable

import numpy as np
from gymnasium import Env, spaces

from eigenfrequencies.config_yaml import ConfigError


class EigenfreqEnv(Env):
    """RL environment for eigenfrequency (structural resonance) optimisation.

    Wraps the same objective interface used by DE / CMA-ES / PSO /
    Bayesian backends so an RL agent competes on the identical fitness
    landscape.  Each :meth:`step` maps a normalised action ``[-1, 1]``
    to a design vector, evaluates the objective, and returns a reward of
    ``-objective`` (higher is better — the agent maximises reward to
    minimise the physical objective).

    Attributes:
        action_space: Box(-1, 1, shape=(dim,))
        observation_space: Box(-inf, inf, shape=(dim+1,)) —
            first *dim* entries are the design vector normalised to
            [0, 1]; the last entry is the most recent objective value.
    """

    metadata = {"render_modes": []}

    def __init__(
        self,
        bounds: list[tuple[float, float]],
        objective_fn: Callable[[np.ndarray], float],
        max_evals: int = 200,
        target_objective: float | None = None,
    ) -> None:
        """Create the environment.

        Args:
            bounds: ``[(min, max), ...]`` one tuple per design dimension.
                ``min > max`` raises :exc:`ConfigError` at construction.
            objective_fn: maps a design vector (``np.ndarray`` of length
                *dim*) to a scalar objective (lower is better).  Use the
                same function the other optimisers call (e.g. a wrapper
                around :func:`eigenfrequencies.penalty.objective.combined_objective`).
            max_evals: maximum number of :meth:`step` calls per episode.
            target_objective: optional early-termination threshold —
                episode ends when ``objective <= target_objective``.
        """
        super().__init__()

        if not bounds:
            raise ConfigError("bounds must not be empty")
        for i, (lo, hi) in enumerate(bounds):
            if lo > hi:
                raise ConfigError(
                    f"Invalid bounds at dimension {i}: "
                    f"min ({lo}) > max ({hi})"
                )

        self._bounds_low = np.array([b[0] for b in bounds], dtype=np.float64)
        self._bounds_high = np.array([b[1] for b in bounds], dtype=np.float64)
        self._bounds_range = self._bounds_high - self._bounds_low
        self._dim = len(bounds)

        self._objective_fn = objective_fn
        self._max_evals = max_evals
        self._target_objective = target_objective

        self.action_space = spaces.Box(
            low=-1.0, high=1.0, shape=(self._dim,), dtype=np.float32
        )

        self.observation_space = spaces.Box(
            low=-np.inf, high=np.inf, shape=(self._dim + 1,), dtype=np.float32
        )

        # Internal state — populated in reset()
        self._current_design: np.ndarray | None = None
        self._current_objective: float = 0.0
        self._step_count: int = 0

    # ------------------------------------------------------------------
    # Coordinate transforms
    # ------------------------------------------------------------------

    def _normalise_design(self, design: np.ndarray) -> np.ndarray:
        """Map design from [min, max] to [0, 1]."""
        return (design - self._bounds_low) / self._bounds_range

    def _denormalise_action(self, action: np.ndarray) -> np.ndarray:
        """Map action from [-1, 1] to the raw design bounds."""
        return self._bounds_low + (action + 1.0) / 2.0 * self._bounds_range

    def _build_obs(self) -> np.ndarray:
        """Normalised design vector + last objective value."""
        norm = self._normalise_design(self._current_design)
        return np.append(norm, self._current_objective).astype(np.float32)

    # ------------------------------------------------------------------
    # Gymnasium API
    # ------------------------------------------------------------------

    def reset(self, seed: int | None = None, options: dict | None = None):
        """Reset for a new episode.

        Samples a random initial design uniformly within bounds using
        ``self.np_random`` so that ``reset(seed=42)`` is deterministic.
        """
        super().reset(seed=seed)

        self._current_design = self.np_random.uniform(
            low=self._bounds_low, high=self._bounds_high
        ).astype(np.float64)
        self._current_objective = 0.0
        self._step_count = 0

        return self._build_obs(), {}

    def step(self, action: np.ndarray):
        """Execute one optimisation step.

        Args:
            action: normalised vector in ``[-1, 1]`` (one per dim).

        Returns:
            (obs, reward, terminated, truncated, info) where:
            - **obs**: normalised design + current objective.
            - **reward**: ``-objective(design)``.
            - **terminated**: :data:`True` when ``step_count >= max_evals``
              or the target objective is reached.
            - **truncated**: always :data:`False`.
            - **info**: ``{"objective": ..., "step": ...}``.
        """
        action = np.asarray(action, dtype=np.float64)
        design = self._denormalise_action(action)
        design = np.clip(design, self._bounds_low, self._bounds_high)

        objective = float(self._objective_fn(design))

        self._current_design = design
        self._current_objective = objective
        self._step_count += 1

        reward = -objective

        terminated = self._step_count >= self._max_evals
        if self._target_objective is not None and objective <= self._target_objective:
            terminated = True
        truncated = False

        return (
            self._build_obs(),
            reward,
            terminated,
            truncated,
            {"objective": objective, "step": self._step_count},
        )
