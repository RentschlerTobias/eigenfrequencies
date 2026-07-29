"""EvaluatorPool ABC and EvaluationError."""

from __future__ import annotations

from abc import ABC, abstractmethod

from eigenfrequencies.optimize.protocol import Design


class EvaluationError(Exception):
    """Raised when a worker fails to evaluate a design after retries.

    Attributes:
        worker_log_path: path to the worker's log file (may be ``None`` for
            remote backends that do not write local logs).
    """

    def __init__(self, message: str, worker_log_path: str | None = None) -> None:
        super().__init__(message)
        self.worker_log_path = worker_log_path


class EvaluatorPool(ABC):
    """Abstract base class for batched design evaluators."""

    @abstractmethod
    def evaluate(self, designs: list[Design]) -> list[float]:
        """Evaluate a batch of designs and return their scalar objectives.

        Args:
            designs: list of :class:`Design` instances to evaluate.

        Returns:
            list of float objectives, one per design, in the same order as
            *designs*.
        """

    @abstractmethod
    def shutdown(self) -> None:
        """Clean shutdown of the pool and its workers."""

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.shutdown()
        return False
