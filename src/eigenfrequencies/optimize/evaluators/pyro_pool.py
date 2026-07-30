"""Pyro5Pool — remote evaluator via Pyro5 RPC with file-based URI discovery.

Ports the Pyro5 daemon + URI-file discovery pattern from
``turbine_runner/server_de.py``.  Pyro5 is imported **lazily** so the module
is importable when Pyro5 is absent.

The ``EVAL_MODE`` environment variable (``combined`` / ``cfd_only`` /
``resonance_only``) is preserved by passing it through to the remote
workers — the remote ``Evaluator`` reads it from its own environment, so
we simply ensure the local env is consistent.
"""

from __future__ import annotations

import os
import tempfile
import time
from typing import TYPE_CHECKING

from eigenfrequencies.optimize.protocol import Design
from eigenfrequencies.optimize.evaluators.base import EvaluatorPool, EvaluationError

if TYPE_CHECKING:
    import Pyro5.api


class Pyro5Pool(EvaluatorPool):
    """Pyro5 RPC evaluator pool with shared-filesystem URI discovery.

    Args:
        uri_dir: directory where workers write ``worker_<id>.uri`` files.
            Defaults to the ``DE_URI_DIR`` environment variable, or a
            temporary directory under ``tempfile.gettempdir()``.
        n_workers: expected number of workers.  If ``None``, the pool waits
            for at least one worker.
        timeout: seconds to wait for worker discovery (default 600).
        poll_interval: seconds between URI directory polls (default 2).
        labels: design parameter labels passed to the remote evaluator.
            If ``None``, an empty list is sent.
    """

    def __init__(
        self,
        uri_dir: str | None = None,
        n_workers: int | None = None,
        timeout: int = 600,
        poll_interval: int = 2,
        labels: list[str] | None = None,
    ) -> None:
        default_dir = os.path.join(tempfile.gettempdir(), "pyro5_uris")
        self.uri_dir = uri_dir or os.environ.get("DE_URI_DIR", default_dir)
        self.n_workers = n_workers or 1
        self.timeout = timeout
        self.poll_interval = poll_interval
        self.labels = labels or []
        self._uris: list[str] = []

    def _discover(self) -> list[str]:
        """Poll *uri_dir* until *n_workers* ``*.uri`` files appear.

        Reproduces the discovery logic from
        ``turbine_runner/optimize_de.py::_discover_servers``.
        """
        deadline = time.time() + self.timeout
        uris: list[str] = []
        while True:
            if os.path.isdir(self.uri_dir):
                uris = []
                for fname in sorted(os.listdir(self.uri_dir)):
                    if not fname.endswith(".uri"):
                        continue
                    fpath = os.path.join(self.uri_dir, fname)
                    try:
                        with open(fpath) as fh:
                            u = fh.read().strip()
                    except OSError:
                        continue
                    if u.startswith("PYRO:"):
                        uris.append(u)
                if len(uris) >= self.n_workers:
                    return uris
            if time.time() > deadline:
                break
            time.sleep(self.poll_interval)
        return uris

    def _evaluate_remote(
        self, uri: str, design_vector: list[float]
    ) -> tuple[float, dict | None]:
        """Call a remote Pyro5 worker synchronously.

        Creates a fresh proxy per call to avoid Pyro5 ownership issues.
        """
        import Pyro5.api  # lazy import — only evaluated at runtime

        with Pyro5.api.Proxy(uri) as proxy:
            return proxy.evaluate(design_vector, self.labels)

    def evaluate(self, designs: list[Design]) -> list[float]:
        """Dispatch designs to remote Pyro5 workers round-robin."""
        import Pyro5.api  # lazy import

        if not self._uris:
            self._uris = self._discover()
            if not self._uris:
                raise EvaluationError(
                    f"No Pyro5 workers discovered in {self.uri_dir} "
                    f"after {self.timeout}s"
                )

        n_workers = len(self._uris)
        from concurrent.futures import ThreadPoolExecutor, as_completed

        with ThreadPoolExecutor(max_workers=n_workers) as pool:
            futures: dict = {}
            for i, design in enumerate(designs):
                future = pool.submit(
                    self._evaluate_remote,
                    self._uris[i % n_workers],
                    design.vector,
                )
                futures[future] = i

            results: list[float | None] = [None] * len(designs)
            for future in as_completed(futures):
                i = futures[future]
                try:
                    obj, _brk = future.result(timeout=900)
                    results[i] = float(obj)
                except Exception as exc:
                    raise EvaluationError(
                        f"Pyro5 worker error for design {i}: {exc}"
                    ) from exc

        return [r for r in results if r is not None]

    def shutdown(self) -> None:
        """Release any cached Pyro5 proxies."""
        # Proxies are created per-call and auto-released by the context
        # manager inside _evaluate_remote, so there is no persistent state
        # to clean up here.
        self._uris = []

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.shutdown()
        return False
