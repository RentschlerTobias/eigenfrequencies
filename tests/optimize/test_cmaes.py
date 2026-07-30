"""Tests for the CMA-ES backend.

Covers:
* Sphere-function convergence
* Seeded determinism
* state_dict / load_state roundtrip
* Graceful degradation when ``cma`` is not installed
"""

from unittest.mock import patch

import numpy as np
import pytest

from eigenfrequencies.optimize.backends.cmaes import CMAESOptimizer
from eigenfrequencies.optimize.protocol import ProtocolUsageError, create


def _sphere(v: list[float]) -> float:
    """2-D sphere function (minimum 0 at origin)."""
    x = np.asarray(v, dtype=float)
    return float(np.sum(x ** 2))


def _run_cmaes(bounds, seed, budget):
    """Helper: run CMA-ES for *budget* evaluations and return best objective."""
    cfg = {"bounds": bounds, "seed": seed}
    opt = CMAESOptimizer(cfg)

    popsize = opt._es.popsize
    evals = 0
    while evals < budget:
        n = min(popsize, budget - evals)
        designs = opt.ask(n)
        objs = [_sphere(d.vector) for d in designs]
        opt.tell(designs, objs)
        evals += n

    return opt._es.result.fbest


class TestCMAESSphere:
    """CMA-ES on the 2-D sphere function."""

    def test_reaches_within_budget_100(self):
        """CMA-ES with budget 100 drives the sphere close to zero."""
        bounds = [(-5.0, 5.0), (-5.0, 5.0)]
        best = _run_cmaes(bounds, seed=42, budget=100)
        assert best < 1e-3, f"best={best}"


class TestCMAESDeterminism:
    """Seeded reproducibility."""

    def test_same_seed_same_ask_sequence(self):
        bounds = [(-1.0, 1.0), (-1.0, 1.0)]
        cfg = {"bounds": bounds, "seed": 123}

        opt_a = CMAESOptimizer(cfg)
        opt_b = CMAESOptimizer(cfg)

        da = opt_a.ask(6)
        db = opt_b.ask(6)
        assert [d.vector for d in da] == [d.vector for d in db]

        # After one tell
        objs = [float(i) for i in range(6)]
        opt_a.tell(da, objs)
        opt_b.tell(db, objs)

        da2 = opt_a.ask(6)
        db2 = opt_b.ask(6)
        assert [d.vector for d in da2] == [d.vector for d in db2]

    def test_different_seed_different_ask(self):
        bounds = [(-1.0, 1.0), (-1.0, 1.0)]
        a = CMAESOptimizer({"bounds": bounds, "seed": 1}).ask(6)
        b = CMAESOptimizer({"bounds": bounds, "seed": 2}).ask(6)
        assert [d.vector for d in a] != [d.vector for d in b]


class TestCMAESStateRoundtrip:
    """state_dict → load_state reproduces exact next ask."""

    def test_roundtrip_after_initial_tell(self):
        bounds = [(-1.0, 1.0), (-1.0, 1.0)]
        cfg = {"bounds": bounds, "seed": 7}

        opt1 = CMAESOptimizer(cfg)
        d1 = opt1.ask(6)
        opt1.tell(d1, [float(i) for i in range(6)])

        state = opt1.state_dict()

        opt2 = CMAESOptimizer({"bounds": [(0.0, 1.0)], "seed": 999})
        opt2.load_state(state)

        next1 = opt1.ask(6)
        next2 = opt2.ask(6)
        assert [d.vector for d in next1] == [d.vector for d in next2]

    def test_roundtrip_after_multiple_generations(self):
        bounds = [(-1.0, 1.0), (-1.0, 1.0)]
        cfg = {"bounds": bounds, "seed": 99}

        opt1 = CMAESOptimizer(cfg)
        for _ in range(3):
            d = opt1.ask(6)
            opt1.tell(d, [float(np.sum(np.asarray(v.vector) ** 2)) for v in d])

        state = opt1.state_dict()

        opt2 = CMAESOptimizer({"bounds": [(0.0, 1.0)], "seed": 999})
        opt2.load_state(state)

        next1 = opt1.ask(6)
        next2 = opt2.ask(6)
        assert [d.vector for d in next1] == [d.vector for d in next2]

    def test_roundtrip_preserves_best(self):
        bounds = [(-1.0, 1.0), (-1.0, 1.0)]
        opt = CMAESOptimizer({"bounds": bounds, "seed": 5})
        d = opt.ask(6)
        opt.tell(d, [float(i) for i in range(6)])

        state = opt.state_dict()
        opt2 = CMAESOptimizer({"bounds": [(0.0, 1.0)], "seed": 999})
        opt2.load_state(state)

        assert opt2._es.result.fbest == opt._es.result.fbest
        assert opt2._es.result.xbest.tolist() == opt._es.result.xbest.tolist()


class TestCMAESProtocolErrors:
    """Mismatched tell lengths."""

    def test_tell_mismatched_raises(self):
        opt = CMAESOptimizer({"bounds": [(0.0, 1.0), (0.0, 1.0)], "seed": 1})
        d = opt.ask(5)
        with pytest.raises(ProtocolUsageError):
            opt.tell(d, [1.0, 2.0])


class TestCMAESBounds:
    """Bounds property and behaviour."""

    def test_bounds_property(self):
        bounds = [(-2.0, 3.0), (0.0, 1.0)]
        opt = CMAESOptimizer({"bounds": bounds})
        assert opt.bounds == bounds

    def test_solutions_stay_inside_bounds(self):
        bounds = [(-1.0, 1.0), (-1.0, 1.0)]
        opt = CMAESOptimizer({"bounds": bounds, "seed": 1})
        for _ in range(5):
            d = opt.ask(6)
            for v in d:
                assert all(bounds[i][0] <= v.vector[i] <= bounds[i][1] for i in range(2))
            opt.tell(d, [float(i) for i in range(6)])


class TestCMAESUnavailable:
    """Graceful degradation when ``cma`` is not installed."""

    def test_import_without_cma_reports_unavailable(self):
        """Creating ``cmaes`` via registry when ``cma`` is absent must raise
        ``ImportError`` with a clear message."""
        with patch.dict("sys.modules", {"cma": None}):
            # Force re-import of the module so the top-level ``import cma`` fails.
            import importlib

            import eigenfrequencies.optimize.backends.cmaes as cmaes_mod

            importlib.reload(cmaes_mod)
            with pytest.raises(ImportError, match="unavailable: cma not installed"):
                cmaes_mod.CMAESOptimizer({"bounds": [(0.0, 1.0)]})

    def test_registry_reports_unavailable(self):
        """``create("cmaes", ...)`` with ``cma`` missing must raise a clear error."""
        with patch.dict("sys.modules", {"cma": None}):
            import importlib

            import eigenfrequencies.optimize as opt_pkg
            import eigenfrequencies.optimize.backends.cmaes as cmaes_mod

            importlib.reload(cmaes_mod)
            # Re-register the factory with the freshly reloaded module.
            opt_pkg.register("cmaes", lambda cfg: cmaes_mod.CMAESOptimizer(cfg))

            with pytest.raises(ImportError, match="unavailable: cma not installed"):
                create("cmaes", {"bounds": [(0.0, 1.0)]})
