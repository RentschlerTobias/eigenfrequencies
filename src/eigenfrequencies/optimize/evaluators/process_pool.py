"""ProcessPoolEvaluator — local ProcessPoolExecutor with worker isolation.

Ports the ``ProcessPoolExecutor`` + ``$TMPDIR/worker_{id}/`` isolation
pattern from ``turbine_runner/optimize_de.py`` (legacy host-side evaluation).
"""

from __future__ import annotations

import os
import tempfile
from concurrent.futures import ProcessPoolExecutor
from typing import Callable

from eigenfrequencies.optimize.evaluators.base import EvaluationError, EvaluatorPool
from eigenfrequencies.optimize.protocol import Design


def _eval_single(
    worker_id: int,
    design_vector: list[float],
    evaluator: Callable[[Design], float],
    tmpdir: str,
) -> float:
    """Worker function: evaluate one design in an isolated directory.

    Creates ``$TMPDIR/worker_{id}/`` (or a ``tempfile.mkdtemp`` fallback)
    so that subprocesses spawned by the evaluator (dtOO, OpenFOAM, etc.)
    do not collide with other workers.
    """
    worker_dir = os.path.join(tmpdir, f"worker_{worker_id}")
    os.makedirs(worker_dir, exist_ok=True)
    log_path = os.path.join(worker_dir, "eval.log")

    # Isolate this worker's TMPDIR so any subprocesses it launches write
    # into a private directory.  This mirrors the legacy ``_worker_dir()``
    # helper in ``turbine_runner/legacy/optimize.py``.
    old_tmpdir = os.environ.get("TMPDIR")
    os.environ["TMPDIR"] = worker_dir

    try:
        design = Design(vector=list(design_vector))
        result = evaluator(design)
        with open(log_path, "a") as log_fh:
            log_fh.write(f"OK result={result}\n")
        return float(result)
    except Exception as exc:
        with open(log_path, "a") as log_fh:
            log_fh.write(f"ERROR: {exc}\n")
        raise
    finally:
        if old_tmpdir is not None:
            os.environ["TMPDIR"] = old_tmpdir
        elif "TMPDIR" in os.environ:
            del os.environ["TMPDIR"]


class ProcessPool(EvaluatorPool):
    """Local process-pool evaluator with per-worker directory isolation.

    Args:
        evaluator: callable that receives a single :class:`Design` and returns
            a float objective.
        n_workers: number of worker processes.  Defaults to ``os.cpu_count()``.
    """

    def __init__(
        self,
        evaluator: Callable[[Design], float],
        n_workers: int | None = None,
    ) -> None:
        self.evaluator = evaluator
        self.n_workers = n_workers or os.cpu_count() or 1
        self._executor: ProcessPoolExecutor | None = None
        self._tmpdir: str | None = None

    def _ensure_started(self) -> None:
        if self._executor is None:
            self._tmpdir = tempfile.mkdtemp(prefix="eval_pool_")
            self._executor = ProcessPoolExecutor(max_workers=self.n_workers)

    def evaluate(self, designs: list[Design]) -> list[float]:
        """Evaluate *designs* in parallel, retrying once on worker failure."""
        self._ensure_started()
        assert self._tmpdir is not None
        assert self._executor is not None

        results: list[float] = []
        for i, design in enumerate(designs):
            worker_id = i % self.n_workers
            args = (worker_id, design.vector, self.evaluator, self._tmpdir)

            last_exc: Exception | None = None
            for attempt in range(2):
                try:
                    future = self._executor.submit(_eval_single, *args)
                    result = future.result()
                    results.append(result)
                    break
                except Exception as exc:
                    last_exc = exc
                    if attempt == 0:
                        continue  # retry once
                    # Retry exhausted — raise EvaluationError with log path
                    worker_dir = os.path.join(self._tmpdir, f"worker_{worker_id}")
                    log_path = os.path.join(worker_dir, "eval.log")
                    raise EvaluationError(
                        f"Worker {worker_id} failed after 1 retry: {last_exc}",
                        worker_log_path=log_path,
                    ) from last_exc

        return results

    def shutdown(self) -> None:
        if self._executor is not None:
            self._executor.shutdown(wait=True)
            self._executor = None
        # Intentionally do NOT delete self._tmpdir so logs survive for debugging.

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.shutdown()
        return False
