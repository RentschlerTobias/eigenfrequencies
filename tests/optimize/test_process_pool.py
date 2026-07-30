"""Tests for ProcessPool evaluator.

Covers:
* DE sphere convergence through the pool (reproduces todo-24 result)
* Worker exception retry-then-error behaviour
* Context-manager support
* Per-worker directory isolation
"""

from __future__ import annotations

import os

import numpy as np
import pytest

from eigenfrequencies.optimize.backends.de import DEOptimizer
from eigenfrequencies.optimize.evaluators.base import EvaluationError
from eigenfrequencies.optimize.evaluators.process_pool import ProcessPool
from eigenfrequencies.optimize.protocol import Design


def _sphere(design: Design) -> float:
    """2-D sphere function (minimum 0 at origin)."""
    x = np.asarray(design.vector, dtype=float)
    return float(np.sum(x ** 2))


def _touch_file(design: Design) -> float:
    """Write a marker file into the worker's isolated TMPDIR."""
    tmpdir = os.environ.get("TMPDIR", "/tmp")
    marker = os.path.join(tmpdir, "marker.txt")
    with open(marker, "w") as fh:
        fh.write("ok")
    return 0.0


# Module-level mutable state for testing retry behaviour across worker
# process boundaries.  ProcessPoolExecutor workers import this module once
# and keep it in memory, so the dict persists between calls.
_retry_state: dict[str, int] = {"call_count": 0}


class AlwaysFail:
    """Picklable evaluator that always raises."""

    def __call__(self, design: Design) -> float:
        raise RuntimeError("always fails")


def _flaky_once(design: Design) -> float:
    """Module-level evaluator that fails on its first call in a worker process.

    The module-level counter is reset to 0 when the worker process imports
    this module, so the first call in a fresh worker raises; the retry
    (second call in the same worker) succeeds.
    """
    _retry_state["call_count"] += 1
    if _retry_state["call_count"] == 1:
        raise RuntimeError(f"simulated failure #{_retry_state['call_count']}")
    return _sphere(design)


class TestProcessPoolSphere:
    """DE + ProcessPool reproduces todo-24 sphere result."""

    def test_reaches_1e6_within_default_budget(self):
        """Default DE budget (pop 20 * max_gen 30 = 600 evals) drives sphere < 1e-6."""
        bounds = [(-5.0, 5.0), (-5.0, 5.0)]
        opt = DEOptimizer({"bounds": bounds, "seed": 42})

        with ProcessPool(_sphere, n_workers=2) as pool:
            pop_size = opt._pop_size
            designs = opt.ask(pop_size)
            objs = pool.evaluate(designs)
            opt.tell(designs, objs)

            remaining = 600 - pop_size
            while remaining > 0:
                n = min(pop_size, remaining)
                designs = opt.ask(n)
                objs = pool.evaluate(designs)
                opt.tell(designs, objs)
                remaining -= n

        assert opt._best_obj < 1e-6, f"best={opt._best_obj}"

    def test_reaches_1e6_with_x0(self):
        """x0-based init also converges within default budget through the pool."""
        bounds = [(-2.0, 2.0), (-2.0, 2.0)]
        opt = DEOptimizer({"bounds": bounds, "seed": 42, "x0": [0.5, -0.5]})

        with ProcessPool(_sphere, n_workers=2) as pool:
            pop_size = opt._pop_size
            designs = opt.ask(pop_size)
            objs = pool.evaluate(designs)
            opt.tell(designs, objs)

            remaining = 600 - pop_size
            while remaining > 0:
                n = min(pop_size, remaining)
                designs = opt.ask(n)
                objs = pool.evaluate(designs)
                opt.tell(designs, objs)
                remaining -= n

        assert opt._best_obj < 1e-6, f"best={opt._best_obj}"


class TestProcessPoolRetry:
    """Worker exception triggers retry once, then EvaluationError."""

    def test_retry_once_then_succeed(self):
        """First call fails, retry succeeds."""
        _retry_state["call_count"] = 0
        with ProcessPool(_flaky_once, n_workers=1) as pool:
            result = pool.evaluate([Design(vector=[1.0, 2.0])])
        assert result == [5.0]  # 1^2 + 2^2

        worker_dir = os.path.join(pool._tmpdir, "worker_0")
        log_path = os.path.join(worker_dir, "eval.log")
        assert os.path.isfile(log_path)
        with open(log_path) as fh:
            log = fh.read()
        assert log.count("ERROR:") == 1
        assert log.count("OK result=") == 1

    def test_two_failures_raise_evaluation_error(self):
        """Two consecutive failures raise EvaluationError with log path."""
        with ProcessPool(AlwaysFail(), n_workers=1) as pool:
            with pytest.raises(EvaluationError) as exc_info:
                pool.evaluate([Design(vector=[1.0])])

        exc = exc_info.value
        assert "Worker 0 failed after 1 retry" in str(exc)
        assert exc.worker_log_path is not None
        assert os.path.isfile(exc.worker_log_path)


class TestProcessPoolIsolation:
    """Per-worker directory isolation."""

    def test_worker_dirs_created(self):
        """Each worker gets a ``worker_{id}/`` subdirectory."""
        with ProcessPool(_touch_file, n_workers=2) as pool:
            pool.evaluate([Design(vector=[1.0]), Design(vector=[2.0])])

        # After the pool exits, the tmpdir should still exist (we don't delete
        # it so logs survive).  Verify worker subdirs were created.
        assert pool._tmpdir is not None
        for worker_id in range(2):
            worker_dir = os.path.join(pool._tmpdir, f"worker_{worker_id}")
            assert os.path.isdir(worker_dir)
            marker = os.path.join(worker_dir, "marker.txt")
            assert os.path.isfile(marker)


class TestProcessPoolContextManager:
    """Context manager support."""

    def test_enter_returns_self(self):
        pool = ProcessPool(_sphere, n_workers=1)
        assert pool.__enter__() is pool

    def test_exit_shuts_down(self):
        pool = ProcessPool(_sphere, n_workers=1)
        pool.evaluate([Design(vector=[1.0])])
        pool.__exit__(None, None, None)
        assert pool._executor is None
