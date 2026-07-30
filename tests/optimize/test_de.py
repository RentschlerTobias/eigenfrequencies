"""Tests for the Differential Evolution backend.

Covers:
* Sphere-function convergence
* Seeded determinism
* state_dict / load_state roundtrip
* Environment-variable override of defaults
"""

import os

import numpy as np
import pytest

from eigenfrequencies.optimize.backends.de import DEOptimizer
from eigenfrequencies.optimize.protocol import ProtocolUsageError


def _sphere(v: list[float]) -> float:
    """2-D sphere function (minimum 0 at origin)."""
    x = np.asarray(v, dtype=float)
    return float(np.sum(x ** 2))


def _run_de(bounds, seed, budget, x0=None):
    """Helper: run DE for *budget* evaluations and return best objective."""
    cfg = {"bounds": bounds, "seed": seed}
    if x0 is not None:
        cfg["x0"] = x0
    opt = DEOptimizer(cfg)

    pop_size = opt._pop_size
    # Generation 0
    designs = opt.ask(pop_size)
    objs = [_sphere(d.vector) for d in designs]
    opt.tell(designs, objs)

    # Subsequent generations
    remaining = budget - pop_size
    while remaining > 0:
        n = min(pop_size, remaining)
        designs = opt.ask(n)
        objs = [_sphere(d.vector) for d in designs]
        opt.tell(designs, objs)
        remaining -= n

    return opt._best_obj


class TestDESphere:
    """DE on the 2-D sphere function."""

    def test_reaches_1e6_within_default_budget(self):
        """Default DE budget (pop 20 * max_gen 30 = 600 evals) drives sphere < 1e-6."""
        bounds = [(-5.0, 5.0), (-5.0, 5.0)]
        best = _run_de(bounds, seed=42, budget=600)
        assert best < 1e-6, f"best={best}"

    def test_reaches_1e6_with_x0(self):
        """x0-based init also converges within default budget."""
        bounds = [(-2.0, 2.0), (-2.0, 2.0)]
        best = _run_de(bounds, seed=42, budget=600, x0=[0.5, -0.5])
        assert best < 1e-6, f"best={best}"


class TestDEDeterminism:
    """Seeded reproducibility."""

    def test_same_seed_same_ask_sequence(self):
        bounds = [(-1.0, 1.0), (-1.0, 1.0)]
        cfg = {"bounds": bounds, "seed": 123}

        opt_a = DEOptimizer(cfg)
        opt_b = DEOptimizer(cfg)

        # Initial ask
        da = opt_a.ask(10)
        db = opt_b.ask(10)
        assert [d.vector for d in da] == [d.vector for d in db]

        # After one tell
        objs = [float(i) for i in range(10)]
        opt_a.tell(da, objs)
        opt_b.tell(db, objs)

        da2 = opt_a.ask(10)
        db2 = opt_b.ask(10)
        assert [d.vector for d in da2] == [d.vector for d in db2]

    def test_different_seed_different_ask(self):
        bounds = [(-1.0, 1.0), (-1.0, 1.0)]
        a = DEOptimizer({"bounds": bounds, "seed": 1}).ask(10)
        b = DEOptimizer({"bounds": bounds, "seed": 2}).ask(10)
        assert [d.vector for d in a] != [d.vector for d in b]


class TestDEStateRoundtrip:
    """state_dict → load_state reproduces exact next ask."""

    def test_roundtrip_after_initial_tell(self):
        bounds = [(-1.0, 1.0), (-1.0, 1.0)]
        cfg = {"bounds": bounds, "seed": 7}

        opt1 = DEOptimizer(cfg)
        d1 = opt1.ask(10)
        opt1.tell(d1, [float(i) for i in range(10)])

        state = opt1.state_dict()

        opt2 = DEOptimizer({"bounds": [(0.0, 0.0)], "seed": 999})
        opt2.load_state(state)

        next1 = opt1.ask(10)
        next2 = opt2.ask(10)
        assert [d.vector for d in next1] == [d.vector for d in next2]

    def test_roundtrip_after_multiple_generations(self):
        bounds = [(-1.0, 1.0), (-1.0, 1.0)]
        cfg = {"bounds": bounds, "seed": 99}

        opt1 = DEOptimizer(cfg)
        for _ in range(3):
            d = opt1.ask(10)
            opt1.tell(d, [float(np.sum(np.asarray(v.vector) ** 2)) for v in d])

        state = opt1.state_dict()

        opt2 = DEOptimizer({"bounds": [(0.0, 0.0)], "seed": 999})
        opt2.load_state(state)

        next1 = opt1.ask(10)
        next2 = opt2.ask(10)
        assert [d.vector for d in next1] == [d.vector for d in next2]

    def test_roundtrip_preserves_best(self):
        bounds = [(-1.0, 1.0), (-1.0, 1.0)]
        opt = DEOptimizer({"bounds": bounds, "seed": 5})
        d = opt.ask(10)
        opt.tell(d, [float(i) for i in range(10)])

        state = opt.state_dict()
        opt2 = DEOptimizer({"bounds": [(0.0, 0.0)], "seed": 999})
        opt2.load_state(state)

        assert opt2._best_obj == opt._best_obj
        assert opt2._best_vec.tolist() == opt._best_vec.tolist()
        assert opt2._generation == opt._generation


class TestDEEnvOverrides:
    """Environment variables override config dict defaults."""

    def test_de_pop_size_override(self, monkeypatch):
        monkeypatch.setenv("DE_POP_SIZE", "42")
        opt = DEOptimizer({"bounds": [(0.0, 1.0)], "pop_size": 10})
        assert opt._pop_size == 42

    def test_de_f_override(self, monkeypatch):
        monkeypatch.setenv("DE_F", "0.5")
        opt = DEOptimizer({"bounds": [(0.0, 1.0)], "F": 0.9})
        assert opt._F == 0.5

    def test_de_cr_override(self, monkeypatch):
        monkeypatch.setenv("DE_CR", "0.7")
        opt = DEOptimizer({"bounds": [(0.0, 1.0)], "CR": 0.99})
        assert opt._CR == 0.7

    def test_de_max_gen_override(self, monkeypatch):
        monkeypatch.setenv("DE_MAX_GEN", "100")
        opt = DEOptimizer({"bounds": [(0.0, 1.0)], "max_generations": 5})
        assert opt._max_gen == 100

    def test_defaults_without_env(self, monkeypatch):
        # Ensure envs are absent
        for key in ("DE_POP_SIZE", "DE_F", "DE_CR", "DE_MAX_GEN"):
            monkeypatch.delenv(key, raising=False)
        opt = DEOptimizer({"bounds": [(0.0, 1.0)]})
        assert opt._pop_size == 20
        assert opt._F == 0.8
        assert opt._CR == 0.9
        assert opt._max_gen == 30


class TestDEProtocolErrors:
    """Mismatched tell lengths."""

    def test_tell_mismatched_raises(self):
        opt = DEOptimizer({"bounds": [(0.0, 1.0), (0.0, 1.0)], "seed": 1})
        d = opt.ask(5)
        with pytest.raises(ProtocolUsageError):
            opt.tell(d, [1.0, 2.0])


class TestDEBounds:
    """Bounds property and clipping behaviour."""

    def test_bounds_property(self):
        bounds = [(-2.0, 3.0), (0.0, 1.0)]
        opt = DEOptimizer({"bounds": bounds})
        assert opt.bounds == bounds

    def test_trials_stay_inside_bounds(self):
        bounds = [(-1.0, 1.0), (-1.0, 1.0)]
        opt = DEOptimizer({"bounds": bounds, "seed": 1})
        d0 = opt.ask(20)
        opt.tell(d0, [float(i) for i in range(20)])
        for _ in range(5):
            d = opt.ask(20)
            for v in d:
                assert all(bounds[i][0] <= v.vector[i] <= bounds[i][1] for i in range(2))
            opt.tell(d, [float(i) for i in range(20)])

    def test_x0_init_respects_bounds(self):
        bounds = [(0.0, 1.0), (0.0, 1.0)]
        opt = DEOptimizer({"bounds": bounds, "seed": 1, "x0": [0.5, 0.5]})
        d = opt.ask(20)
        for v in d:
            assert all(0.0 <= v.vector[i] <= 1.0 for i in range(2))
