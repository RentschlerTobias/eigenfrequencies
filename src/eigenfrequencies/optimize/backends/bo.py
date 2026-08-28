"""Bayesian Optimisation backend using Optuna's TPE sampler via the ask/tell API.

Recommended for expensive CFD-in-loop evaluations where each evaluation takes
minutes to hours.  Tree-structured Parzen Estimator (TPE) builds a surrogate
model from completed trials and proposes the next design vectors where the
expected improvement is highest, making it far more sample-efficient than
population-based methods such as Differential Evolution for small budgets
(≤ 50–100 evaluations).

Usage::

    from eigenfrequencies.optimize import create
    opt = create("bo", {"bounds": [(-5.0, 5.0), (-5.0, 5.0)], "seed": 42})
    designs = opt.ask(5)          # 5 design vectors to evaluate in parallel
    objectives = [expensive_func(d.vector) for d in designs]
    opt.tell(designs, objectives)  # feed results back to the surrogate

The backend is registered under the name ``"bo"``.  If *optuna* is not
installed the module is still importable, but instantiating ``BOOptimizer``
raises a clear runtime error.
"""

from __future__ import annotations

from typing import Any

from eigenfrequencies.optimize.protocol import Design, Optimizer, ProtocolUsageError


class BOOptimizer(Optimizer):
    """Bayesian Optimisation via Optuna TPESampler (ask/tell interface).

    Args:
        config: dict-like object with keys:
            - ``bounds``: list of (min, max) tuples (required)
            - ``seed``: int seed for the TPESampler RNG (default None)
            - ``direction``: ``"minimize"`` or ``"maximize"`` (default ``"minimize"``)
            - ``n_startup_trials``: number of random trials before TPE kicks in
              (default 5)
    """

    def __init__(self, config: Any = None) -> None:
        # Imported here rather than at module scope so the module stays importable
        # without optuna, and so a re-import under a patched sys.modules cannot
        # bake a stale "unavailable" flag into the class.
        try:
            import optuna
        except ImportError:
            raise RuntimeError(
                "BOOptimizer unavailable: optuna not installed. "
                "Install with: pip install optuna"
            ) from None

        self._optuna = optuna

        cfg = config or {}
        self._bounds: list[tuple[float, float]] = list(cfg.get("bounds", []))
        if not self._bounds:
            raise ValueError("BOOptimizer requires 'bounds' in config")

        self._dim = len(self._bounds)
        self._seed = cfg.get("seed")
        self._direction = cfg.get("direction", "minimize")
        self._n_startup_trials = int(cfg.get("n_startup_trials", 5))

        self._study = self._create_study()
        self._pending_trials: list[Any] = []

    # ── Protocol ──

    @property
    def bounds(self) -> list[tuple[float, float]]:
        return list(self._bounds)

    def ask(self, n: int) -> list[Design]:
        """Return *n* design vectors proposed by the TPE surrogate."""
        # Clear any stale pending trials (caller should have told previous batch)
        self._pending_trials = []

        designs: list[Design] = []
        for _ in range(n):
            trial = self._study.ask()
            vector = [
                trial.suggest_float(f"x{i}", low, high)
                for i, (low, high) in enumerate(self._bounds)
            ]
            designs.append(Design(vector=vector))
            self._pending_trials.append(trial)
        return designs

    def tell(self, designs: list[Design], objectives: list[float]) -> None:
        if len(designs) != len(objectives):
            raise ProtocolUsageError(
                f"designs ({len(designs)}) and objectives ({len(objectives)}) "
                "must have the same length"
            )
        if len(designs) != len(self._pending_trials):
            raise ProtocolUsageError(
                f"tell() received {len(designs)} designs but "
                f"ask() returned {len(self._pending_trials)} trials"
            )

        for trial, obj in zip(self._pending_trials, objectives):
            self._study.tell(trial, obj)
        self._pending_trials = []

    def state_dict(self) -> dict:
        """Serializable state for checkpointing.

        Captures the study configuration, all completed trials, and the internal
        RNG states of the TPE sampler so that the surrogate can be resumed
        exactly after ``load_state``.
        """
        trials: list[dict[str, Any]] = []
        for trial in self._study.trials:
            if trial.state == self._optuna.trial.TrialState.COMPLETE:
                trials.append(
                    {
                        "params": trial.params,
                        "value": trial.value,
                    }
                )
        return {
            "bounds": self._bounds,
            "seed": self._seed,
            "direction": self._direction,
            "n_startup_trials": self._n_startup_trials,
            "trials": trials,
            "sampler_rng_state": self._get_sampler_rng_state(),
        }

    def load_state(self, state: dict) -> None:
        """Restore optimizer state from a dict produced by ``state_dict``."""
        self._bounds = [tuple(b) for b in state["bounds"]]
        self._dim = len(self._bounds)
        self._seed = state.get("seed")
        self._direction = state.get("direction", "minimize")
        self._n_startup_trials = int(state.get("n_startup_trials", 5))
        self._pending_trials = []

        self._study = self._create_study()
        distributions = {
            f"x{i}": self._optuna.distributions.FloatDistribution(low, high)
            for i, (low, high) in enumerate(self._bounds)
        }
        for trial_data in state.get("trials", []):
            trial = self._optuna.trial.create_trial(
                state=self._optuna.trial.TrialState.COMPLETE,
                params=trial_data["params"],
                distributions=distributions,
                value=trial_data["value"],
            )
            self._study.add_trial(trial)

        self._set_sampler_rng_state(state.get("sampler_rng_state"))

    # ── Internals ──

    def _create_study(self) -> Any:
        """Build a fresh Optuna Study with TPESampler."""
        sampler = self._optuna.samplers.TPESampler(
            seed=self._seed,
            n_startup_trials=self._n_startup_trials,
        )
        return self._optuna.create_study(
            direction=self._direction,
            sampler=sampler,
        )

    def _get_sampler_rng_state(self) -> dict[str, Any]:
        """Capture the internal RNG states of the TPESampler."""
        sampler = self._study.sampler
        states: dict[str, Any] = {}
        if hasattr(sampler, "_rng") and hasattr(sampler._rng, "rng"):
            states["_rng"] = sampler._rng.rng.get_state()
        if (
            hasattr(sampler, "_random_sampler")
            and hasattr(sampler._random_sampler, "_rng")
            and hasattr(sampler._random_sampler._rng, "rng")
        ):
            states["_random_sampler._rng"] = sampler._random_sampler._rng.rng.get_state()
        return states

    def _set_sampler_rng_state(self, states: dict[str, Any] | None) -> None:
        """Restore the internal RNG states of the TPESampler."""
        if states is None:
            return
        sampler = self._study.sampler
        if "_rng" in states and hasattr(sampler, "_rng") and hasattr(sampler._rng, "rng"):
            sampler._rng.rng.set_state(states["_rng"])
        if (
            "_random_sampler._rng" in states
            and hasattr(sampler, "_random_sampler")
            and hasattr(sampler._random_sampler, "_rng")
            and hasattr(sampler._random_sampler._rng, "rng")
        ):
            sampler._random_sampler._rng.rng.set_state(states["_random_sampler._rng"])
