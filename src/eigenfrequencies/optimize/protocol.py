"""Optimizer protocol: ask/tell ABC, Design dataclass, registry, and errors.

The ask/tell pattern decouples the optimizer from the objective function.
The optimizer proposes design vectors via ``ask()``; the caller evaluates them
and feeds scalar objectives back via ``tell()``.  State can be checkpointed
with ``state_dict()`` / ``load_state()``.
"""

from __future__ import annotations

import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable


class ProtocolUsageError(Exception):
    """Raised when the optimizer protocol is used incorrectly."""


@dataclass(frozen=True)
class Design:
    """A single design vector proposed by an optimizer.

    Attributes:
        vector: list of float design parameters
        metadata: optional caller-supplied metadata (not touched by the optimizer)
    """
    vector: list[float]
    metadata: dict = field(default_factory=dict)


class Optimizer(ABC):
    """Abstract base class for ask/tell optimizers.

    Subclasses must implement ``ask``, ``tell``, ``state_dict``,
    ``load_state``, and the ``bounds`` property.
    """

    @abstractmethod
    def ask(self, n: int) -> list[Design]:
        """Return *n* design vectors to evaluate.

        The first call typically returns an initial population; subsequent
        calls return trial vectors derived from the internal state.
        """

    @abstractmethod
    def tell(self, designs: list[Design], objectives: list[float]) -> None:
        """Consume evaluated objectives for the designs returned by the last ``ask``.

        Raises:
            ProtocolUsageError: if ``len(designs) != len(objectives)``.
        """

    @abstractmethod
    def state_dict(self) -> dict:
        """Return a serializable dict representing the optimizer state."""

    @abstractmethod
    def load_state(self, state: dict) -> None:
        """Restore optimizer state from a dict produced by ``state_dict``."""

    @property
    @abstractmethod
    def bounds(self) -> list[tuple[float, float]]:
        """List of (min, max) bound tuples, one per design dimension."""


# ── Registry ──

_REGISTRY: dict[str, Callable[[Any], Optimizer]] = {}


def register(name: str, factory: Callable[[Any], Optimizer]) -> None:
    """Register an optimizer backend under *name*.

    *factory* receives the config dict/object and must return an
    :class:`Optimizer` instance.
    """
    _REGISTRY[name] = factory


def create(name: str, config: Any = None) -> Optimizer:
    """Instantiate the optimizer registered under *name*.

    Args:
        name: registered backend name (e.g. ``"de"``)
        config: opaque config passed to the factory

    Raises:
        ValueError: if *name* is not registered.
    """
    if name not in _REGISTRY:
        registered = list(_REGISTRY.keys())
        raise ValueError(f"Unknown optimizer '{name}'. Registered: {registered}")
    return _REGISTRY[name](config)
