"""Tests for the PSO backend.

Covers:
* Sphere-function convergence
* Seeded determinism
* state_dict / load_state roundtrip
* Graceful degradation when pymoo is not installed
* Bounds property and ProtocolUsageError on mismatched tell
"""

import sys
from typing import Any

import numpy as np
import pytest

from eigenfrequencies.optimize.backends.pso import PSOOptimizer
from eigenfrequencies.optimize.protocol import Design, ProtocolUsageError, create, register


def _sphere(v: list[float]) -> float:
    """2-D sphere function (minimum 0 at origin)."""
    x = np.asarray(v, dtype=float)
    return float(np.sum(x ** 2))


def _run_pso(bounds, seed, budget):
    """Helper: run PSO for *budget* evaluations and return best objective."""
    cfg = {"bounds": bounds, "seed": seed, "pop_size": 10}
    opt = PSOOptimizer(cfg)

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

    # Best objective from the algorithm's opt population
    return float(opt._algorithm.opt[0].F[0])


class TestPSOSphere:
    """PSO on the 2-D sphere function."""

    def test_reaches_1e6_within_budget_500(self):
        """Budget 500 (pop 10 * 50 gen) drives sphere < 1e-6."""
        bounds = [(-5.0, 5.0), (-5.0, 5.0)]
        best = _run_pso(bounds, seed=42, budget=500)
        assert best < 1e-6, f"best={best}"


class TestPSODeterminism:
    """Seeded reproducibility."""

    def test_same_seed_same_ask_sequence(self):
        bounds = [(-1.0, 1.0), (-1.0, 1.0)]
        cfg = {"bounds": bounds, "seed": 123, "pop_size": 10}

        opt_a = PSOOptimizer(cfg)
        opt_b = PSOOptimizer(cfg)

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
        a = PSOOptimizer({"bounds": bounds, "seed": 1, "pop_size": 10}).ask(10)
        b = PSOOptimizer({"bounds": bounds, "seed": 2, "pop_size": 10}).ask(10)
        assert [d.vector for d in a] != [d.vector for d in b]


class TestPSOStateRoundtrip:
    """state_dict → load_state reproduces exact next ask."""

    def test_roundtrip_after_initial_tell(self):
        bounds = [(-1.0, 1.0), (-1.0, 1.0)]
        cfg = {"bounds": bounds, "seed": 7, "pop_size": 10}

        opt1 = PSOOptimizer(cfg)
        d1 = opt1.ask(10)
        opt1.tell(d1, [float(i) for i in range(10)])

        state = opt1.state_dict()

        opt2 = PSOOptimizer({"bounds": [(0.0, 0.0)], "seed": 999})
        opt2.load_state(state)

        next1 = opt1.ask(10)
        next2 = opt2.ask(10)
        assert [d.vector for d in next1] == [d.vector for d in next2]

    def test_roundtrip_after_multiple_generations(self):
        bounds = [(-1.0, 1.0), (-1.0, 1.0)]
        cfg = {"bounds": bounds, "seed": 99, "pop_size": 10}

        opt1 = PSOOptimizer(cfg)
        for _ in range(3):
            d = opt1.ask(10)
            opt1.tell(d, [float(np.sum(np.asarray(v.vector) ** 2)) for v in d])

        state = opt1.state_dict()

        opt2 = PSOOptimizer({"bounds": [(0.0, 0.0)], "seed": 999})
        opt2.load_state(state)

        next1 = opt1.ask(10)
        next2 = opt2.ask(10)
        assert [d.vector for d in next1] == [d.vector for d in next2]

    def test_roundtrip_preserves_best(self):
        bounds = [(-1.0, 1.0), (-1.0, 1.0)]
        opt = PSOOptimizer({"bounds": bounds, "seed": 5, "pop_size": 10})
        d = opt.ask(10)
        opt.tell(d, [float(i) for i in range(10)])

        state = opt.state_dict()
        opt2 = PSOOptimizer({"bounds": [(0.0, 0.0)], "seed": 999})
        opt2.load_state(state)

        assert float(opt2._algorithm.opt[0].F[0]) == float(opt._algorithm.opt[0].F[0])
        assert opt2._generation == opt._generation


class TestPSOUnavailable:
    """Graceful degradation when pymoo is missing."""

    def test_import_without_pymoo_does_not_crash(self, monkeypatch):
        """Removing pymoo from sys.modules should not break the import."""
        # Temporarily hide pymoo
        monkeypatch.setitem(sys.modules, "pymoo", None)
        monkeypatch.setitem(sys.modules, "pymoo.algorithms", None)
        monkeypatch.setitem(sys.modules, "pymoo.algorithms.soo", None)
        monkeypatch.setitem(sys.modules, "pymoo.algorithms.soo.nonconvex", None)
        monkeypatch.setitem(sys.modules, "pymoo.algorithms.soo.nonconvex.pso", None)
        monkeypatch.setitem(sys.modules, "pymoo.core", None)
        monkeypatch.setitem(sys.modules, "pymoo.core.problem", None)
        # Force re-import of the pso module. Use monkeypatch.delitem so the entry
        # is restored on teardown — a raw `del` leaks into whichever test runs
        # next and breaks namespace-path recalculation (KeyError on the parent).
        monkeypatch.delitem(
            sys.modules, "eigenfrequencies.optimize.backends.pso", raising=False
        )
        from eigenfrequencies.optimize.backends.pso import PSOOptimizer as PSO2

        with pytest.raises(RuntimeError, match="unavailable: pymoo not installed"):
            PSO2({})

    def test_registry_reports_unavailable_when_pymoo_missing(self, monkeypatch):
        """Creating 'pso' without pymoo raises a clear error."""
        monkeypatch.setitem(sys.modules, "pymoo", None)
        monkeypatch.setitem(sys.modules, "pymoo.algorithms", None)
        monkeypatch.setitem(sys.modules, "pymoo.algorithms.soo", None)
        monkeypatch.setitem(sys.modules, "pymoo.algorithms.soo.nonconvex", None)
        monkeypatch.setitem(sys.modules, "pymoo.algorithms.soo.nonconvex.pso", None)
        monkeypatch.setitem(sys.modules, "pymoo.core", None)
        monkeypatch.setitem(sys.modules, "pymoo.core.problem", None)
        # Force re-import. monkeypatch.delitem restores both entries on teardown;
        # dropping "eigenfrequencies.optimize" with a raw `del` poisons the parent
        # package for later tests in this session.
        for mod in (
            "eigenfrequencies.optimize.backends.pso",
            "eigenfrequencies.optimize",
        ):
            monkeypatch.delitem(sys.modules, mod, raising=False)
        from eigenfrequencies.optimize import create as create2

        with pytest.raises(RuntimeError, match="unavailable: pymoo not installed"):
            create2("pso", {"bounds": [(-1.0, 1.0)]})


class TestPSOProtocolErrors:
    """Mismatched tell lengths and missing metadata."""

    def test_tell_mismatched_raises(self):
        opt = PSOOptimizer({"bounds": [(0.0, 1.0), (0.0, 1.0)], "seed": 1, "pop_size": 10})
        d = opt.ask(5)
        with pytest.raises(ProtocolUsageError):
            opt.tell(d, [1.0, 2.0])

    def test_tell_without_ask_raises(self):
        opt = PSOOptimizer({"bounds": [(0.0, 1.0)], "seed": 1, "pop_size": 10})
        with pytest.raises(ProtocolUsageError):
            opt.tell([Design(vector=[0.5])], [1.0])

    def test_tell_missing_metadata_raises(self):
        opt = PSOOptimizer({"bounds": [(0.0, 1.0), (0.0, 1.0)], "seed": 1, "pop_size": 10})
        d = opt.ask(5)
        # Strip metadata
        d_bad = [Design(vector=v.vector) for v in d]
        with pytest.raises(ProtocolUsageError, match="_pso_idx"):
            opt.tell(d_bad, [1.0, 2.0, 3.0, 4.0, 5.0])


class TestPSOBounds:
    """Bounds property and clipping behaviour."""

    def test_bounds_property(self):
        bounds = [(-2.0, 3.0), (0.0, 1.0)]
        opt = PSOOptimizer({"bounds": bounds, "pop_size": 10})
        assert opt.bounds == bounds

    def test_trials_stay_inside_bounds(self):
        bounds = [(-1.0, 1.0), (-1.0, 1.0)]
        opt = PSOOptimizer({"bounds": bounds, "seed": 1, "pop_size": 10})
        d0 = opt.ask(10)
        opt.tell(d0, [float(i) for i in range(10)])
        for _ in range(5):
            d = opt.ask(10)
            for v in d:
                assert all(bounds[i][0] <= v.vector[i] <= bounds[i][1] for i in range(2))
            opt.tell(d, [float(i) for i in range(10)])


class TestPSOPartialEvaluation:
    """PSO supports ask/tell with n < pop_size."""

    def test_partial_ask_returns_remaining(self):
        bounds = [(-1.0, 1.0), (-1.0, 1.0)]
        opt = PSOOptimizer({"bounds": bounds, "seed": 1, "pop_size": 10})

        # Ask for 3
        d1 = opt.ask(3)
        assert len(d1) == 3
        opt.tell(d1, [1.0, 2.0, 3.0])

        # Ask for 4 (should get 4 of the remaining 7)
        d2 = opt.ask(4)
        assert len(d2) == 4
        opt.tell(d2, [4.0, 5.0, 6.0, 7.0])

        # Ask for 10 (should get remaining 3)
        d3 = opt.ask(10)
        assert len(d3) == 3
        opt.tell(d3, [8.0, 9.0, 10.0])

        # Now the generation is complete; next ask returns fresh offspring
        d4 = opt.ask(5)
        assert len(d4) == 5

    def test_partial_ask_advances_after_full_tell(self):
        bounds = [(-1.0, 1.0), (-1.0, 1.0)]
        opt = PSOOptimizer({"bounds": bounds, "seed": 1, "pop_size": 10})

        gen_before = opt._generation

        # Evaluate in two batches
        d1 = opt.ask(5)
        opt.tell(d1, [float(i) for i in range(5)])
        assert opt._generation == gen_before  # not yet advanced

        d2 = opt.ask(10)
        assert len(d2) == 5  # remaining 5
        opt.tell(d2, [float(i) for i in range(5)])
        assert opt._generation == gen_before + 1  # now advanced
