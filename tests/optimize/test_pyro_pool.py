"""Tests for Pyro5Pool evaluator.

Loopback integration test: starts a local Pyro5 daemon, writes its URI to a
file, and verifies Pyro5Pool discovers and evaluates through it.

Skipped when Pyro5 is not installed.
"""

from __future__ import annotations

import os
import sys
import tempfile
import threading
import time

import pytest

from eigenfrequencies.optimize.evaluators.pyro_pool import Pyro5Pool
from eigenfrequencies.optimize.evaluators.base import EvaluationError
from eigenfrequencies.optimize.protocol import Design

# Skip the entire module if Pyro5 is absent.
pytest.importorskip("Pyro5", reason="Pyro5 not installed")

import Pyro5.api  # noqa: E402
import Pyro5.server  # noqa: E402


@Pyro5.api.expose
class LoopbackEvaluator:
    """Simple evaluator for loopback testing — computes the sphere function."""

    def evaluate(self, x_list, labels):
        obj = sum(v ** 2 for v in x_list)
        return obj, {"total": obj, "eval_mode": "loopback"}


@pytest.fixture
def uri_dir(tmp_path):
    """Temporary URI directory for a single test."""
    d = tmp_path / "uris"
    d.mkdir()
    return str(d)


@pytest.fixture
def daemon(uri_dir):
    """Start a local Pyro5 daemon and publish its URI.

    Yields the URI string.  The daemon is shut down after the test.
    """
    host = "localhost"
    Pyro5.config.HOST = host

    daemon = Pyro5.server.Daemon(host)
    uri = daemon.register(LoopbackEvaluator)

    # Atomic publish (write temp then rename)
    uri_path = os.path.join(uri_dir, "worker_0.uri")
    tmp_path = uri_path + ".tmp"
    with open(tmp_path, "w") as fh:
        fh.write(str(uri))
    os.replace(tmp_path, uri_path)

    # Run the request loop in a background thread
    thread = threading.Thread(target=daemon.requestLoop, daemon=True)
    thread.start()
    time.sleep(0.2)  # give the daemon time to start listening

    yield str(uri)

    daemon.shutdown()


@pytest.mark.requires_dtoo
class TestPyro5PoolLoopback:
    """Pyro5Pool loopback integration test."""

    def test_discover_and_evaluate_single(self, uri_dir, daemon):
        """Discover one worker and evaluate a single design."""
        pool = Pyro5Pool(uri_dir=uri_dir, n_workers=1, timeout=5)
        with pool:
            result = pool.evaluate([Design(vector=[3.0, 4.0])])
        assert result == [25.0]  # 3^2 + 4^2

    def test_discover_and_evaluate_batch(self, uri_dir, daemon):
        """Evaluate a batch of designs round-robin across one worker."""
        pool = Pyro5Pool(uri_dir=uri_dir, n_workers=1, timeout=5)
        with pool:
            designs = [
                Design(vector=[1.0, 0.0]),
                Design(vector=[0.0, 2.0]),
                Design(vector=[3.0, 4.0]),
            ]
            results = pool.evaluate(designs)
        assert results == [1.0, 4.0, 25.0]

    def test_no_workers_raises(self, uri_dir):
        """Empty URI directory raises EvaluationError quickly."""
        pool = Pyro5Pool(uri_dir=uri_dir, n_workers=1, timeout=1)
        with pytest.raises(EvaluationError, match="No Pyro5 workers"):
            with pool:
                pool.evaluate([Design(vector=[1.0])])

    def test_context_manager(self, uri_dir, daemon):
        """Context manager enters and exits cleanly."""
        pool = Pyro5Pool(uri_dir=uri_dir, n_workers=1, timeout=5)
        with pool as p:
            assert p is pool
            result = pool.evaluate([Design(vector=[2.0])])
        assert result == [4.0]
        assert pool._uris == []  # shutdown clears URIs
