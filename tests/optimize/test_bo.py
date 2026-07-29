"""Tests for the Bayesian Optimisation (BO / TPE) backend.

Covers:
* 2-D quadratic sample-efficiency vs DE at the same budget
* Seeded determinism
* state_dict / load_state roundtrip
* Graceful degradation when optuna is not installed
* Bounds property and ProtocolUsageError on mismatched tell
"""

import sys
from typing import Any

import numpy as np
import pytest

from eigenfrequencies.optimize.backends.bo import BOOptimizer
from eigenfrequencies.optimize.protocol import Design, ProtocolUsageError, create, register


def _quadratic(v: list[float]) -> float:
    """2-D shifted quadratic (minimum 0 at [1.0, -1.0])."""
    x = np.asarray(v, dtype=float)
    target = np.array([1.0, -1.0])
    return float(np.sum((x - target) ** 2))


def _run_bo(bounds, seed, budget):
    """Helper: run BO for *budget* evaluations and return best objective."""
    opt = BOOptimizer({"bounds": bounds, "seed": seed})
    for _ in range(budget):
        designs = opt.ask(1)
        objs = [_quadratic(d.vector) for d in designs]
        opt.tell(designs, objs)
    # best value among completed trials
    return opt._study.best_value


def _run_de(bounds, seed, budget):
    """Helper: run DE for *budget* evaluations and return best objective."""
    from eigenfrequencies.optimize.backends.de import DEOptimizer

    cfg = {"bounds": bounds, "seed": seed}
    opt = DEOptimizer(cfg)
    pop_size = opt._pop_size
    designs = opt.ask(pop_size)
    objs = [_quadratic(d.vector) for d in designs]
    opt.tell(designs, objs)
    remaining = budget - pop_size
    while remaining > 0:
        n = min(pop_size, remaining)
        designs = opt.ask(n)
        objs = [_quadratic(d.vector) for d in designs]
        opt.tell(designs, objs)
        remaining -= n
    return opt._best_obj


class TestBOSampleEfficiency:
    """BO should beat DE on a low budget for a smooth quadratic."""

    def test_bo_beats_de_at_budget_30(self):
        """On a 2-D quadratic with budget 30, BO best < DE best."""
        bounds = [(-5.0, 5.0), (-5.0, 5.0)]
        bo_best = _run_bo(bounds, seed=42, budget=30)
        de_best = _run_de(bounds, seed=42, budget=30)
        assert bo_best < de_best, f"BO best={bo_best} not better than DE best={de_best}"


class TestBODeterminism:
    """Seeded reproducibility."""

    def test_same_seed_same_ask_sequence(self):
        bounds = [(-1.0, 1.0), (-1.0, 1.0)]
        cfg = {"bounds": bounds, "seed": 123}

        opt_a = BOOptimizer(cfg)
        opt_b = BOOptimizer(cfg)

        da = opt_a.ask(5)
        db = opt_b.ask(5)
        assert [d.vector for d in da] == [d.vector for d in db]

        objs = [float(i) for i in range(5)]
        opt_a.tell(da, objs)
        opt_b.tell(db, objs)

        da2 = opt_a.ask(5)
        db2 = opt_b.ask(5)
        assert [d.vector for d in da2] == [d.vector for d in db2]

    def test_different_seed_different_ask(self):
        bounds = [(-1.0, 1.0), (-1.0, 1.0)]
        a = BOOptimizer({"bounds": bounds, "seed": 1}).ask(5)
        b = BOOptimizer({"bounds": bounds, "seed": 2}).ask(5)
        assert [d.vector for d in a] != [d.vector for d in b]


class TestBOStateRoundtrip:
    """state_dict → load_state reproduces exact next ask."""

    def test_roundtrip_after_initial_tell(self):
        bounds = [(-1.0, 1.0), (-1.0, 1.0)]
        cfg = {"bounds": bounds, "seed": 7}

        opt1 = BOOptimizer(cfg)
        d1 = opt1.ask(3)
        opt1.tell(d1, [1.0, 2.0, 3.0])

        state = opt1.state_dict()

        opt2 = BOOptimizer({"bounds": [(0.0, 0.0)], "seed": 999})
        opt2.load_state(state)

        next1 = opt1.ask(3)
        next2 = opt2.ask(3)
        assert [d.vector for d in next1] == [d.vector for d in next2]

    def test_roundtrip_after_multiple_tells(self):
        bounds = [(-1.0, 1.0), (-1.0, 1.0)]
        cfg = {"bounds": bounds, "seed": 99}

        opt1 = BOOptimizer(cfg)
        for _ in range(5):
            d = opt1.ask(2)
            opt1.tell(d, [float(np.sum(np.asarray(v.vector) ** 2)) for v in d])

        state = opt1.state_dict()

        opt2 = BOOptimizer({"bounds": [(0.0, 0.0)], "seed": 999})
        opt2.load_state(state)

        next1 = opt1.ask(2)
        next2 = opt2.ask(2)
        assert [d.vector for d in next1] == [d.vector for d in next2]

    def test_roundtrip_preserves_best(self):
        bounds = [(-1.0, 1.0), (-1.0, 1.0)]
        opt = BOOptimizer({"bounds": bounds, "seed": 5})
        d = opt.ask(3)
        opt.tell(d, [3.0, 1.0, 2.0])

        state = opt.state_dict()
        opt2 = BOOptimizer({"bounds": [(0.0, 0.0)], "seed": 999})
        opt2.load_state(state)

        assert opt2._study.best_value == opt._study.best_value


class TestBOUnavailable:
    """Graceful degradation when optuna is missing."""

    def test_import_without_optuna_does_not_crash(self, monkeypatch):
        """Removing optuna from sys.modules should not break the import."""
        # Temporarily hide optuna
        monkeypatch.setitem(sys.modules, "optuna", None)
        # Force re-import of the bo module
        mod_name = "eigenfrequencies.optimize.backends.bo"
        if mod_name in sys.modules:
            del sys.modules[mod_name]
        from eigenfrequencies.optimize.backends.bo import BOOptimizer as BO2

        with pytest.raises(RuntimeError, match="unavailable: optuna not installed"):
            BO2({})

    def test_registry_reports_unavailable_when_optuna_missing(self, monkeypatch):
        """Creating 'bo' without optuna raises a clear error."""
        monkeypatch.setitem(sys.modules, "optuna", None)
        mod_name = "eigenfrequencies.optimize.backends.bo"
        if mod_name in sys.modules:
            del sys.modules[mod_name]
        # Re-import __init__ so the lambda is fresh
        init_name = "eigenfrequencies.optimize"
        if init_name in sys.modules:
            del sys.modules[init_name]
        from eigenfrequencies.optimize import create as create2

        with pytest.raises(RuntimeError, match="unavailable: optuna not installed"):
            create2("bo", {"bounds": [(-1.0, 1.0)]})


class TestBOProtocolErrors:
    """Mismatched tell lengths."""

    def test_tell_mismatched_raises(self):
        opt = BOOptimizer({"bounds": [(0.0, 1.0), (0.0, 1.0)], "seed": 1})
        d = opt.ask(3)
        with pytest.raises(ProtocolUsageError):
            opt.tell(d, [1.0, 2.0])

    def test_tell_without_ask_raises(self):
        opt = BOOptimizer({"bounds": [(0.0, 1.0)], "seed": 1})
        with pytest.raises(ProtocolUsageError):
            opt.tell([Design(vector=[0.5])], [1.0])


class TestBOBounds:
    """Bounds property and clipping behaviour."""

    def test_bounds_property(self):
        bounds = [(-2.0, 3.0), (0.0, 1.0)]
        opt = BOOptimizer({"bounds": bounds})
        assert opt.bounds == bounds

    def test_trials_stay_inside_bounds(self):
        bounds = [(-1.0, 1.0), (-1.0, 1.0)]
        opt = BOOptimizer({"bounds": bounds, "seed": 1})
        for _ in range(10):
            d = opt.ask(5)
            for v in d:
                assert all(bounds[i][0] <= v.vector[i] <= bounds[i][1] for i in range(2))
            opt.tell(d, [float(i) for i in range(5)])
